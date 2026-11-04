"""Evaluate a checkpoint the way the hub2 anonymisation service uses it (docs/PLAN.md, 2026-11 plan step 5).

One `extract_entities_long` call per text with the service's label list and word-chunk size, then the service's
post-processing: confidence >= threshold, labels that stay visible (court, date, legal norm, country) are dropped,
location/organization spans that are country names are dropped, and of nested spans the longest wins.
Scored on characters and mentions, which is what matters for pseudonymisation:

- `char_recall`: share of gold PII characters that end up masked.
- `leaked_mentions`: share of gold PII mentions with at least one character left visible.
- `char_precision`: share of masked characters that are gold PII (only for sources that annotate every PII label).
- `visible_masked`: share of characters of visible gold spans (courts, dates, norms, countries) that got masked.

    python -m legalner.prodeval out/v3/best data/canonical/gold_at.jsonl data/test/obdk_synth/obdk_synth_test.docs.jsonl \
        --chunk-sizes 96,384 --out out/eval/prod_v3.json
"""
import argparse
import collections
import json
import pathlib
import time

from legalner.build import read_records
from legalner.relabel import COUNTRIES, _norm
from legalner.schema import DERIVED, SOURCES

# the service's query, in its order (labels as prompt strings)
PROD_QUERY = ["person", "organization", "address", "street", "location", "case number", "bank account",
              "social security number", "tax id", "company register number", "license plate", "land register id",
              "id document number", "other identifier", "phone number", "email", "date of birth", "court", "date",
              "legal norm", "country"]
VISIBLE = {"court", "date", "legal_norm", "country"}
# what the service masks: everything it queries except the visible labels (roles are always also person)
PII = {q.replace(" ", "_") for q in PROD_QUERY} - VISIBLE


def covered(rec):
    """Labels the record's source annotates, roles included (they are always also person)."""
    src = SOURCES[rec["source"]]
    labels = set(src.coverage) | {d for d, base in DERIVED.items() if base in src.coverage}
    return labels - set(rec.get("meta", {}).get("uncovered", ()))


def predict_cands(model, text, chunk_size, threshold=0.5, query=PROD_QUERY):
    """Candidate spans [(start, end, label, confidence)] of one service call, before thresholds and nesting."""
    res = model.extract_entities_long(text, query, threshold=threshold, chunk_size=chunk_size,
                                      chunk_overlap=max(8, chunk_size // 4), include_spans=True,
                                      include_confidence=True)
    cands = []
    for name, mentions in res.get("entities", res).items():
        lab = name.replace(" ", "_")
        for m in mentions:  # visible labels are kept as candidates: they protect text from name propagation
            if lab in ("location", "organization") and _norm(text[m["start"]:m["end"]]) in COUNTRIES:
                continue
            if m["end"] - m["start"] > 1:
                cands.append((m["start"], m["end"], lab, float(m.get("confidence", 1.0))))
    return cands


def select(cands, thresholds=None, default=0.5):
    """The service's post-processing on candidates: per-label threshold, then the longest of nested spans wins."""
    thresholds = thresholds or {}
    cands = [c for c in cands if c[3] >= thresholds.get(c[2], default) and c[2] not in VISIBLE]
    cands.sort(key=lambda c: (-(c[1] - c[0]), -c[3]))
    kept = []
    for c in cands:  # longest span wins over spans inside it
        if not any(k[0] <= c[0] and c[1] <= k[1] for k in kept):
            kept.append(c)
    return [(s, e, lab) for s, e, lab, _ in kept]


def predict_masks(model, text, chunk_size, threshold=0.5, query=PROD_QUERY):
    """Masked spans as the service computes them: [(start, end, label)]."""
    return select(predict_cands(model, text, chunk_size, threshold, query), default=threshold)


def protected(cands, thresholds=None, default=0.5):
    """Spans the model labelled as visible (court, date, legal norm, country): no propagation into them."""
    thresholds = thresholds or {}
    return [(s, e) for s, e, lab, c in cands if lab in VISIBLE and c >= thresholds.get(lab, default)]


def propagate_docs(records, masks, protect=None):
    """Name propagation (legalner.postprocess) over the records of each document."""
    from legalner.postprocess import propagate
    by_doc = collections.defaultdict(list)
    for i, rec in enumerate(records):
        by_doc[rec.get("doc_id", rec["id"])].append(i)
    out = list(masks)
    for idxs in by_doc.values():
        prot = [protect[i] for i in idxs] if protect else None
        for i, m in zip(idxs, propagate([records[i]["text"] for i in idxs], [masks[i] for i in idxs], prot)):
            out[i] = m
    return out


def score(records, masks):
    by = collections.defaultdict(collections.Counter)
    for rec, spans in zip(records, masks):
        cov = covered(rec)
        masked = set()
        for s, e, _ in spans:  # clamp: a model can return offsets past the end of a chunk's text
            masked.update(range(max(0, s), min(e, len(rec["text"]))))
        gold = [g for g in rec["spans"] if g["label"] in PII and g["label"] in cov]
        gold_chars = {i for g in gold for i in range(g["start"], g["end"]) if not rec["text"][i].isspace()}
        vis_chars = {i for g in rec["spans"] if g["label"] in VISIBLE and g["label"] in cov
                     for i in range(g["start"], g["end"]) if not rec["text"][i].isspace()}
        masked_nonspace = {i for i in masked if not rec["text"][i].isspace()}
        for key in ("all", f"source={rec['source']}"):
            c = by[key]
            c["gold_chars"] += len(gold_chars)
            c["hit_chars"] += len(gold_chars & masked)
            c["mentions"] += len(gold)
            c["leaked"] += sum(any(i not in masked and not rec["text"][i].isspace()
                                   for i in range(g["start"], g["end"])) for g in gold)
            c["visible_chars"] += len(vis_chars)
            c["visible_masked"] += len(vis_chars & masked)
            if PII <= cov:  # precision only where every PII label is annotated
                c["masked_chars"] += len(masked_nonspace)
                c["masked_gold"] += len(masked_nonspace & gold_chars)
            for g in gold:
                lc = by[f"label={g['label']}"]
                lc["mentions"] += 1
                lc["leaked"] += any(i not in masked and not rec["text"][i].isspace()
                                    for i in range(g["start"], g["end"]))
    out = {}
    for key, c in sorted(by.items()):
        out[key] = {
            "char_recall": c["hit_chars"] / c["gold_chars"] if c["gold_chars"] else None,
            "leaked_mentions": c["leaked"] / c["mentions"] if c["mentions"] else None,
            "char_precision": c["masked_gold"] / c["masked_chars"] if c["masked_chars"] else None,
            "visible_masked": c["visible_masked"] / c["visible_chars"] if c["visible_chars"] else None,
            "mentions": c["mentions"],
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("data", nargs="+", help="canonical JSONL files (whole documents or chunks)")
    ap.add_argument("--chunk-sizes", default="96,384", help="word chunk sizes of extract_entities_long")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-records", type=int, default=0, help="first N records per file (0 = all)")
    ap.add_argument("--out")
    ap.add_argument("--thresholds", help="JSON {label: threshold} (legalner.thresholds); scored as an extra variant")
    ap.add_argument("--propagate", action="store_true", help="also score with document-level name propagation")
    ap.add_argument("--cands-cache", help="directory for the model's candidates per chunk size (reused if present)")
    ap.add_argument("--onnx", help="run the encoder from this ONNX file (legalner.onnx_export)")
    ap.add_argument("--id-map", help="token id map of a vocabulary-pruned ONNX encoder (.npy)")
    args = ap.parse_args(argv)

    import torch
    from gliner2 import AutoExtractor
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if args.onnx:  # encoder in ONNX Runtime, heads and decoding unchanged (legalner.onnx_export)
        from legalner.onnx_export import load_with_onnx
        model = load_with_onnx(args.model, args.onnx, args.id_map)
    else:
        model = AutoExtractor.from_pretrained(args.model, map_location=device)
        model.eval()
    records = []
    for path in args.data:
        recs = list(read_records([path]))
        records += recs[:args.max_records] if args.max_records else recs
    report = {"model": args.model, "threshold": args.threshold, "n_records": len(records), "data": args.data,
              "query": PROD_QUERY, "by_chunk_size": {}}
    per_label = json.load(open(args.thresholds)) if args.thresholds else None
    query = min([args.threshold, *(per_label or {}).values()])
    for size in (int(x) for x in args.chunk_sizes.split(",")):
        cache = pathlib.Path(args.cands_cache, f"cands_{size}.jsonl") if args.cands_cache else None
        t = time.time()
        if cache and cache.exists():
            got = {d["id"]: [tuple(c) for c in d["cands"]] for d in map(json.loads, cache.open())}
            cands = [got[r["id"]] for r in records]
        else:
            with torch.inference_mode():
                cands = [predict_cands(model, r["text"], size, query) for r in records]
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                with cache.open("w") as fh:
                    for r, c in zip(records, cands):
                        fh.write(json.dumps({"id": r["id"], "cands": c}) + "\n")
        dt = time.time() - t
        variants = {"base": [select(c, default=args.threshold) for c in cands]}
        if per_label:
            variants["thresholds"] = [select(c, per_label, args.threshold) for c in cands]
        if args.propagate:
            variants["propagate"] = propagate_docs(records, variants["base"],
                                                   [protected(c, default=args.threshold) for c in cands])
            if per_label:
                variants["thresholds+propagate"] = propagate_docs(
                    records, variants["thresholds"], [protected(c, per_label, args.threshold) for c in cands])
        report["by_chunk_size"][size] = {}
        print(f"chunk {size}: {sum(len(r['text']) for r in records) / dt:.0f} chars/s")
        for name, masks in variants.items():
            res = score(records, masks)
            report["by_chunk_size"][size][name] = res
            print(f" [{name}]")
            for key, v in res.items():
                if key.startswith(("all", "source=")):
                    fmt = lambda x: "  –  " if x is None else f"{x:.4f}"  # noqa: E731
                    print(f"  {key:28s} recall {fmt(v['char_recall'])}  leaked {fmt(v['leaked_mentions'])}  "
                          f"precision {fmt(v['char_precision'])}  visible-masked {fmt(v['visible_masked'])}  "
                          f"n={v['mentions']}")
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
