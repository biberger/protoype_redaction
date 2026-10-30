"""Merge canonical records from all sources into GLiNER2 train/dev/test files.

Canonical record (one JSON object per line, produced by legalner.tagged and
legalner.sources.*):

    {"id", "source", "doc_id", "lang", "jurisdiction", "text",
     "spans": [{"label", "start", "end", "text"}], "meta": {...}}

Per example, only labels the source covers are queried (schema.SOURCES), so an
unannotated label never becomes a false negative. Training examples get label
augmentation to keep zero-shot behaviour: random subsets of the covered labels,
German/French synonyms as label names and optional descriptions.

    python -m legalner.build data/canonical/*.jsonl data/canonical/ler/*.jsonl -o data/build/v1
"""
import argparse
import collections
import hashlib
import json
import pathlib
import random

from legalner.schema import LABELS, SOURCES

SPLIT_NAMES = {"train": "train", "validation": "dev", "dev": "dev", "test": "test"}


def surface(label):
    return label.replace("_", " ")


def doc_split(rec, dev_frac, test_frac):
    """Use a split given by the source, else a stable hash of the document id."""
    if SOURCES[rec["source"]].eval_only:
        return "test"
    given = rec.get("meta", {}).get("split")
    if given:
        return SPLIT_NAMES[given]
    h = int(hashlib.sha1(rec["doc_id"].encode()).hexdigest(), 16) % 10_000 / 10_000
    return "test" if h < test_frac else "dev" if h < test_frac + dev_frac else "train"


def query_labels(rec):
    """Covered labels for this record minus labels nested unannotated inside a present span."""
    src = SOURCES[rec["source"]]
    if src.open_labels:
        return set(rec["meta"]["query_labels"])
    present = {s["label"] for s in rec["spans"]}
    labels = set(src.coverage) - set(rec.get("meta", {}).get("uncovered", ()))  # per-record gaps (RIS)
    for outer, inner in src.nested_conflicts.items():
        if outer in present:
            labels -= set(inner)
    return labels


def spans_by_label(rec, labels):
    out = collections.defaultdict(list)
    seen = set()
    for s in rec["spans"]:
        key = (s["label"], s["start"], s["end"])
        if s["label"] in labels and key not in seen:
            seen.add(key)
            out[s["label"]].append({"text": s["text"], "start": s["start"], "end": s["end"]})
    return out


def to_example(rec, labels, names=None, descriptions=False):
    """GLiNER2 training record; `names` maps canonical label -> prompt string."""
    names = names or {lab: surface(lab) for lab in labels}
    spans = spans_by_label(rec, labels)
    output = {"entities": {names[lab]: spans.get(lab, []) for lab in sorted(labels)}}
    if descriptions:
        output["entity_descriptions"] = {names[lab]: LABELS[lab].description
                                         for lab in sorted(labels) if lab in LABELS}
    return {"input": rec["text"], "output": output}


def augment(rec, labels, rng, p_keep_pos=0.9, p_keep_neg=0.5, p_rename=0.3, p_desc=0.5):
    """Sample the queried label subset, label wording and descriptions."""
    present = {s["label"] for s in rec["spans"]} & labels
    keep = {lab for lab in labels
            if rng.random() < (p_keep_pos if lab in present else p_keep_neg)}
    if not keep:
        keep = {rng.choice(sorted(labels))}
    names = {}
    rename = rng.random() < p_rename
    for lab in keep:
        synonyms = getattr(LABELS[lab], rec.get("lang", "de"), ()) if rename and lab in LABELS else ()
        names[lab] = rng.choice(synonyms) if synonyms else surface(lab)
    if len(set(names.values())) < len(names):  # synonym collision: fall back to keys
        names = {lab: surface(lab) for lab in keep}
    return to_example(rec, keep, names, descriptions=rng.random() < p_desc and bool(keep & set(LABELS)))


def _same_length_case(text, upper):
    """Upper- or lower-case `text` character by character, keeping characters whose case mapping
    changes the length (ß -> SS, İ -> i̇), so every character offset stays valid."""
    out = []
    for c in text:
        m = c.upper() if upper else c.lower()
        out.append(m if len(m) == 1 else c)
    return "".join(out)


def case_augment(rec, rng):
    """Copy of `rec` with the whole text or single entity spans in ALL CAPS or all lower case
    (letterheads, party blocks, e-mails, OCR). Offsets are unchanged."""
    text = rec["text"]
    mode = rng.choices(("upper", "lower", "spans"), (0.4, 0.3, 0.3))[0]
    if mode != "spans" or not rec["spans"]:
        text = _same_length_case(text, upper=mode != "lower")
    else:
        chosen = {(s["start"], s["end"]) for s in rec["spans"] if rng.random() < 0.5} or \
            {(lambda s: (s["start"], s["end"]))(rng.choice(rec["spans"]))}
        upper = rng.random() < 0.6
        chars = list(text)
        for start, end in chosen:
            chars[start:end] = _same_length_case(text[start:end], upper)
        text = "".join(chars)
    spans = [dict(s, text=text[s["start"]:s["end"]]) for s in rec["spans"]]
    return dict(rec, text=text, spans=spans, meta=dict(rec.get("meta", {}), case_aug=mode))


ABBR_LABELS = ("organization", "court")


def abbreviations(records):
    """doc_id -> {full name: abbreviation} from "Full Name (ABBR)": an organization or court span directly
    followed by a parenthesised, shorter span of the same label (decision 5)."""
    out = collections.defaultdict(dict)
    for rec in records:
        text = rec["text"]
        at = {(s["start"], s["label"]): s for s in rec["spans"]}
        for s in rec["spans"]:
            if s["label"] not in ABBR_LABELS or text[s["end"]:s["end"] + 2] != " (":
                continue
            a = at.get((s["end"] + 2, s["label"]))
            if a and text[a["end"]:a["end"] + 1] == ")" and len(a["text"]) < len(s["text"]):
                out[rec["doc_id"]][s["text"]] = a["text"]
    return out


def abbreviation_augment(rec, abbr, rng, p=0.5):
    """Copy of `rec` where later full-name mentions of an organisation or court are replaced by the abbreviation
    the document defines ("Workplace Relations Commission (WRC)" ... "die WRC"), so the model sees organisations
    referred to by acronym alone (decision 28). The defining mention is kept; offsets are shifted."""
    text = rec["text"]
    keys = {(s["start"], s["end"]) for s in rec["spans"]}
    chosen = {}
    for s in rec["spans"]:
        short = abbr.get(s["text"]) if s["label"] in ABBR_LABELS else None
        if not short or text[s["end"]:s["end"] + len(short) + 3] == f" ({short})" or rng.random() >= p:
            continue
        others = [o for o in rec["spans"] if (o["start"], o["end"]) != (s["start"], s["end"])
                  and o["start"] < s["end"] and s["start"] < o["end"]]
        if not others:
            chosen[(s["start"], s["end"])] = short
    if not chosen:
        return rec
    new_text, shift, pos, moved = [], 0, 0, {}
    for (start, end), short in sorted(chosen.items()):
        new_text.append(text[pos:start] + short)
        moved[(start, end)] = (start + shift, start + shift + len(short))
        shift += len(short) - (end - start)
        pos = end
    new_text.append(text[pos:])
    new_text = "".join(new_text)

    def move(i):  # offset after the replacements that end at or before i
        return i + sum(len(chosen[k]) - (k[1] - k[0]) for k in chosen if k[1] <= i)
    spans = []
    for s in rec["spans"]:
        start, end = moved.get((s["start"], s["end"]), (move(s["start"]), move(s["end"])))
        spans.append(dict(s, start=start, end=end, text=new_text[start:end]))
    assert keys and all(sp["text"] == new_text[sp["start"]:sp["end"]] for sp in spans)
    return dict(rec, text=new_text, spans=spans, meta=dict(rec.get("meta", {}), abbr_aug=len(chosen)))


# boundary_head.max_gold_per_query of gliner2.5-multi-v1 is 64: a batch with more gold spans for one label aborts
# training (TargetCapacityError), so such records are left out of train and dev
MAX_GOLD_PER_LABEL = 60


def too_dense(rec, labels):
    per = collections.Counter(s["label"] for s in rec["spans"] if s["label"] in labels)
    return any(n > MAX_GOLD_PER_LABEL for n in per.values())


def read_records(paths):
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def _per_key(values, cast=int):
    """["ler=16000", "ris:Bundesverwaltungsgericht=800"] -> {key: value}."""
    out = {}
    for v in values or ():
        key, _, n = v.rpartition("=")
        if not key:
            raise SystemExit(f"expected KEY=N, got {v!r}")
        out[key] = cast(n)
    return out


def _chunk_index(rec):
    tail = rec["id"].rpartition("#")[2]
    return int(tail) if tail.isdigit() else 0


def balance(train, rng, max_per_source=0, caps=None, max_per_doc=None, copies=None):
    """Training mix: keep the first `max_per_doc[source]` chunks of each document (the Kopf and facts
    of a decision carry most PII; BVwG country reports do not), cap records per source and per
    `source:court` (`caps`), then repeat records of a source `copies[source]` times."""
    caps, max_per_doc, copies = caps or {}, max_per_doc or {}, copies or {}
    if max_per_doc:
        train = [r for r in train if _chunk_index(r) < max_per_doc.get(r["source"], 10 ** 9)]
    train = list(train)
    rng.shuffle(train)
    kept, per = [], collections.Counter()
    for rec in train:
        keys = [rec["source"], f"{rec['source']}:{rec.get('meta', {}).get('court')}"]
        limits = [caps.get(keys[0], max_per_source or 0), caps.get(keys[1], 0)]
        if any(lim and per[k] >= lim for k, lim in zip(keys, limits)):
            continue
        per.update(keys)
        kept.append(rec)
    return [rec for rec in kept for _ in range(copies.get(rec["source"], 1))]


def source_group(source):
    return "synthetic" if source.startswith("synthetic") else source


def mix(train, rng, shares, anchor="synthetic"):
    """Resample training records to target shares per source group, e.g. {"ler": .4, "synthetic": .3, "ris": .15,
    "replay": .15}. All records of `anchor` are kept once; the total is anchor_count / shares[anchor]. Larger groups
    are subsampled, smaller ones repeated (whole copies plus a random remainder)."""
    groups = collections.defaultdict(list)
    for rec in train:
        groups[source_group(rec["source"])].append(rec)
    missing = set(groups) - set(shares)
    if missing:
        raise SystemExit(f"--mix has no share for {sorted(missing)}")
    total = len(groups[anchor]) / shares[anchor]
    out = []
    for g, recs in sorted(groups.items()):
        want = round(shares[g] * total)
        recs = list(recs)
        rng.shuffle(recs)
        out += recs * (want // len(recs)) + recs[:want % len(recs)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="canonical JSONL files")
    ap.add_argument("-o", "--out", required=True, help="output directory")
    ap.add_argument("--dev-frac", type=float, default=0.1)
    ap.add_argument("--test-frac", type=float, default=0.1)
    ap.add_argument("--copies", type=int, default=1, help="augmented copies per training record")
    ap.add_argument("--max-per-source", type=int, default=0, help="cap training records per source (0 = all)")
    ap.add_argument("--cap", action="append", metavar="KEY=N",
                    help="cap training records of a source or source:court, e.g. ler=16000, "
                         "ris:Bundesverwaltungsgericht=900 (repeatable; overrides --max-per-source)")
    ap.add_argument("--max-per-doc", action="append", metavar="SOURCE=N",
                    help="keep the first N chunks of each document of SOURCE, e.g. ris=60")
    ap.add_argument("--mix", metavar="GROUP=SHARE,...",
                    help="target shares of training records per source group (synthetic* sources form one group), "
                         "applied after --cap/--max-per-doc, e.g. ler=0.4,synthetic=0.3,ris=0.15,replay=0.15")
    ap.add_argument("--source-copies", action="append", metavar="SOURCE=K",
                    help="repeat training records of SOURCE K times (each copy augmented anew)")
    ap.add_argument("--max-eval-per-source", type=int, default=0,
                    help="cap dev/test records per source (0 = all), e.g. for CPU smoke runs")
    ap.add_argument("--exclude-docs", help="file with doc_ids to drop entirely (e.g. data/gold/at/doc_ids.txt)")
    ap.add_argument("--case-frac", type=float, default=0.1,
                    help="share of training examples whose text or single spans are upper/lower-cased")
    ap.add_argument("--abbr-frac", type=float, default=0.5,
                    help="share of training records whose later organisation/court mentions are replaced by the "
                         "abbreviation their document defines")
    ap.add_argument("--validate", action="store_true", help="check every split with gliner2 TrainingDataset.validate()")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    by_split = collections.defaultdict(list)
    excluded = set()
    if args.exclude_docs:
        excluded = {ln.strip() for ln in open(args.exclude_docs, encoding="utf-8") if ln.strip()}
    for rec in read_records(args.inputs):
        if rec["doc_id"] in excluded:
            continue
        if rec["source"] not in SOURCES:
            raise SystemExit(f"{rec['id']}: unknown source {rec['source']!r}; add it to schema.SOURCES")
        by_split[doc_split(rec, args.dev_frac, args.test_frac)].append(rec)

    stats = {}
    train = balance(by_split["train"], rng, args.max_per_source, _per_key(args.cap), _per_key(args.max_per_doc),
                    _per_key(args.source_copies))
    if args.mix:
        train = mix(train, rng, _per_key(args.mix.split(","), float))
    abbr = abbreviations(by_split["train"])
    with (out / "train.jsonl").open("w", encoding="utf-8") as fh:
        n = 0
        for _ in range(args.copies):
            for rec in train:
                labels = query_labels(rec)
                if too_dense(rec, labels):
                    stats["too_dense_skipped"] = stats.get("too_dense_skipped", 0) + 1
                    continue
                if abbr.get(rec["doc_id"]) and rng.random() < args.abbr_frac:
                    rec = abbreviation_augment(rec, abbr[rec["doc_id"]], rng)
                    stats["abbr_augmented"] = stats.get("abbr_augmented", 0) + (rec.get("meta", {}).get("abbr_aug", 0) > 0)
                if rng.random() < args.case_frac:
                    rec = case_augment(rec, rng)
                fh.write(json.dumps(augment(rec, labels, rng), ensure_ascii=False) + "\n")
                n += 1
    stats["train"] = n
    stats["train_per_source"] = dict(collections.Counter(r["source"] for r in train for _ in range(args.copies)))
    stats["train_share"] = {g: round(n / max(1, len(train)), 3) for g, n in
                            collections.Counter(source_group(r["source"]) for r in train).items()}
    for split in ("dev", "test"):
        recs = by_split[split]
        if args.max_eval_per_source:
            per = collections.Counter()
            recs = [r for r in recs if (per.update([r["source"]]) or per[r["source"]]) <= args.max_eval_per_source]
        with (out / f"{split}.jsonl").open("w", encoding="utf-8") as fh:
            for rec in recs:
                if split == "dev" and too_dense(rec, query_labels(rec)):  # dev loss uses the training collator
                    continue
                fh.write(json.dumps(to_example(rec, query_labels(rec)), ensure_ascii=False) + "\n")
        # canonical copy keeps source/jurisdiction for sliced evaluation
        with (out / f"{split}.canonical.jsonl").open("w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats[split] = len(recs)
    stats["records_per_source"] = {
        split: dict(collections.Counter(r["source"] for r in recs)) for split, recs in by_split.items()}
    if args.validate:
        from gliner2.training.data import TrainingDataset
        stats["validate"] = {split: {k: v for k, v in TrainingDataset.load(str(out / f"{split}.jsonl")).validate().items()
                                     if k in ("valid", "invalid", "total")} for split in ("train", "dev", "test")}
    (out / "manifest.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
