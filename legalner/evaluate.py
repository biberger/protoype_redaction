"""Evaluate a GLiNER2 checkpoint on canonical records.

Reports exact-match P/R/F1 per label and per slice (source, jurisdiction) and,
for redaction, character-level recall over PII labels: the share of gold PII
characters covered by any predicted span of any label. Missed characters are
leaked data, so this is the number to watch.

    python -m legalner.evaluate out/run1/best data/build/v1/test.canonical.jsonl --threshold 0.4
"""
import argparse
import collections
import json

from legalner.build import query_labels, read_records, surface
from legalner.schema import LABELS, SOURCES

ROLE_LABELS = {"judge", "lawyer"}


def predict_labels(rec):
    """Labels to ask the model for: the covered labels plus any merged ones."""
    labels = set(query_labels(rec))
    for merged in SOURCES[rec["source"]].eval_merge.values():
        labels |= set(merged)
    return labels


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score(records, predictions):
    """records: canonical records; predictions: per record {label: {(start, end)}}."""
    counts = collections.defaultdict(lambda: [0, 0, 0])  # key -> tp, fp, fn
    pii_gold = pii_hit = 0
    for rec, pred in zip(records, predictions):
        labels = query_labels(rec)
        merge = SOURCES[rec["source"]].eval_merge
        scored = {lab: set().union(*(pred.get(m, set()) for m in merge.get(lab, (lab,)))) for lab in labels}
        gold = collections.defaultdict(set)
        for s in rec["spans"]:
            if s["label"] in labels:
                gold[s["label"]].add((s["start"], s["end"]))
        slices = ("all", f"source={rec['source']}", f"jur={rec['jurisdiction']}")
        for lab in labels:
            g, p = gold.get(lab, set()), scored[lab]
            tp, fp, fn = len(g & p), len(p - g), len(g - p)
            for sl in slices:
                for key in ((sl, lab), (sl, "*")):
                    c = counts[key]
                    c[0] += tp
                    c[1] += fp
                    c[2] += fn
        predicted_chars = {i for spans in pred.values() for s, e in spans for i in range(s, e)}
        gold_pii = {i for lab, spans in gold.items() if lab in LABELS and LABELS[lab].group == "pii"
                    for s, e in spans for i in range(s, e)}
        pii_gold += len(gold_pii)
        pii_hit += len(gold_pii & predicted_chars)
    table = {f"{sl}|{lab}": dict(zip(("p", "r", "f1"), prf(*c)), support=c[0] + c[2])
             for (sl, lab), c in sorted(counts.items())}
    return {"pii_char_recall": pii_hit / pii_gold if pii_gold else None, "scores": table}


def predict(model, records, threshold, batch_size):
    """Run the model on each record with exactly the record's covered labels."""
    preds = []
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        # records in a batch may cover different labels: group by label set
        groups = collections.defaultdict(list)
        for j, rec in enumerate(batch):
            groups[tuple(sorted(predict_labels(rec)))].append(j)
        out = [None] * len(batch)
        for labels, idxs in groups.items():
            for j in idxs:
                out[j] = {}
            # GLiNER2's flat decoding resolves overlaps *across* labels, so a judge would
            # never also come out as person: role labels are queried in a separate pass.
            for part in (set(labels) - ROLE_LABELS, set(labels) & ROLE_LABELS):
                if not part:
                    continue
                names = {surface(lab): lab for lab in part}
                results = model.batch_extract_entities(
                    [batch[j]["text"] for j in idxs], list(names), threshold=threshold,
                    include_spans=True, batch_size=batch_size)
                for j, res in zip(idxs, results):
                    ents = res.get("entities", res)
                    out[j].update({names[name]: {(m["start"], m["end"]) for m in mentions}
                                   for name, mentions in ents.items() if name in names})
        preds.extend(out)
    return preds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="checkpoint dir or Hub id")
    ap.add_argument("data", nargs="+", help="canonical JSONL files")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--device", default=None)
    ap.add_argument("--out", help="write full JSON report here")
    ap.add_argument("--max-per-source", type=int, default=0, help="random sample per source (0 = all)")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args(argv)

    from gliner2 import AutoExtractor
    kwargs = {"map_location": args.device} if args.device else {}
    model = AutoExtractor.from_pretrained(args.model, **kwargs)
    records = list(read_records(args.data))
    if args.max_per_source:
        import random
        by = collections.defaultdict(list)
        for r in records:
            by[r["source"]].append(r)
        rng = random.Random(args.seed)
        records = [r for recs in by.values() for r in rng.sample(recs, min(len(recs), args.max_per_source))]
    report = score(records, predict(model, records, args.threshold, args.batch_size))
    report.update(model=args.model, threshold=args.threshold, n_records=len(records),
                  data=args.data, max_per_source=args.max_per_source, seed=args.seed)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2)
    print(f"PII character recall: {report['pii_char_recall']}")
    for key, s in report["scores"].items():
        if key.endswith("|*") or key.startswith("all|"):
            print(f"{key:45s} P={s['p']:.3f} R={s['r']:.3f} F1={s['f1']:.3f} n={s['support']}")


if __name__ == "__main__":
    main()
