"""Clean dataset export: every canonical source once, relabelled to the final conventions, without augmentation.

Writes one JSONL per source group with a "split" field (train/dev/test by the same document hash as legalner.build),
the evaluation-only sets separately, the label schema and a dataset card. Gold documents are excluded from the
training sources (they are in eval/gold_at.jsonl).

    python -m legalner.export_clean -o data/export/legalner-at-data
"""
import argparse
import collections
import glob
import json
import pathlib
import shutil

from legalner.build import doc_split, read_records, source_group
from legalner.schema import LABELS

TRAIN_SOURCES = ["data/canonical/synthetic_v1.jsonl", "data/canonical/synthetic.jsonl",
                 "data/canonical/synthetic_v3.jsonl", "data/canonical/synthetic_v4.jsonl",
                 "data/canonical/synthetic_v5.jsonl", "data/canonical/synthetic_v6.jsonl",
                 "data/canonical/synthetic_v7.jsonl", "data/canonical/synthetic_v7_grundbuch.jsonl",
                 "data/canonical/synthetic_v7_registers.jsonl", "data/canonical/eurlex.jsonl",
                 "data/canonical/ris.jsonl", "data/canonical/replay.jsonl", *sorted(glob.glob("data/canonical/ler/*.jsonl"))]
EVAL_SETS = {"gold_at.jsonl": "data/canonical/gold_at.jsonl", "mapa_v2.jsonl": "data/canonical/mapa_v2.jsonl",
             "obdk_synth.jsonl": "data/test/obdk_synth/obdk_synth_test.jsonl",
             "regression.jsonl": "data/test/regression/regression.jsonl"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--exclude-docs", default="data/gold/at/doc_ids.txt")
    ap.add_argument("--dev-frac", type=float, default=0.1)
    ap.add_argument("--test-frac", type=float, default=0.1)
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "eval").mkdir(parents=True, exist_ok=True)
    excluded = set(pathlib.Path(args.exclude_docs).read_text().split()) if args.exclude_docs else set()
    stats = collections.defaultdict(collections.Counter)
    labels = collections.defaultdict(collections.Counter)
    files = {}
    for rec in read_records([p for p in TRAIN_SOURCES if pathlib.Path(p).exists()]):
        if rec["doc_id"] in excluded:
            continue
        g = source_group(rec["source"])
        split = doc_split(rec, args.dev_frac, args.test_frac)
        if g not in files:
            files[g] = (out / "data" / f"{g}.jsonl").open("w", encoding="utf-8")
        files[g].write(json.dumps(dict(rec, split=split), ensure_ascii=False) + "\n")
        stats[g][split] += 1
        labels[g].update(s["label"] for s in rec["spans"])
    for f in files.values():
        f.close()
    for name, src in EVAL_SETS.items():
        recs = list(read_records([src]))
        with (out / "eval" / name).open("w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats[f"eval/{name}"]["records"] = len(recs)
    (out / "schema.json").write_text(json.dumps(
        {k: {"description": v.description, "de": list(getattr(v, "de", ()) or ()), "fr": list(getattr(v, "fr", ()) or ())}
         for k, v in LABELS.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "stats.json").write_text(json.dumps({"records": stats, "labels": labels}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    shutil.copy("data/synthetic/GENERATION.md", out / "GENERATION.md")
    print(json.dumps({k: dict(v) for k, v in stats.items()}, indent=1))


if __name__ == "__main__":
    main()
