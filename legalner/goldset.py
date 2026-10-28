"""Austrian gold set: held-out paragraphs, reviewed, never trained on.

Workflow:
1. `select`: sample AT paragraphs (canonical records) stratified by doc type from
   sources that are not yet in a training build, write each as a tagged .md file
   to data/gold/at/pending/ and their document ids to data/gold/at/doc_ids.txt.
   build.py --exclude-docs keeps those whole documents out of train/dev.
2. Review: reviewers (agents, then a human) correct the tags in place, following
   data/synthetic/GENERATION.md, and move the file to data/gold/at/reviewed/.
   A header line `review: agent|human` records who checked it last.
3. `export`: parse reviewed/ with the strict parser into data/canonical/gold_at.jsonl
   (source "gold_at", eval only).

    python -m legalner.goldset select data/canonical/synthetic_v3.jsonl --n 400
    python -m legalner.goldset export
"""
import argparse
import collections
import json
import pathlib
import random

ROOT = pathlib.Path("data/gold/at")


def to_tagged(rec):
    """Canonical record -> inline-tagged text; role spans replace their person duplicate."""
    spans = {}
    for s in rec["spans"]:
        key = (s["start"], s["end"])
        if key not in spans or s["label"] in ("judge", "lawyer"):
            spans[key] = s["label"]
    out, pos = [], 0
    for (s, e), label in sorted(spans.items()):
        if s < pos:  # overlapping spans cannot be written inline; keep the first
            continue
        out.append(rec["text"][pos:s])
        out.append(f"[[{label}|{rec['text'][s:e]}]]")
        pos = e
    out.append(rec["text"][pos:])
    return "".join(out)


def select(paths, n, seed, min_chars=200):
    from legalner.build import read_records
    recs = [r for r in read_records(paths) if r["jurisdiction"] == "AT" and len(r["text"]) >= min_chars]
    by_type = collections.defaultdict(list)
    for r in recs:
        by_type[r["meta"].get("doc_type") or r["meta"].get("court") or "other"].append(r)
    rng = random.Random(seed)
    for v in by_type.values():
        rng.shuffle(v)
    chosen, i = [], 0
    while len(chosen) < n and any(i < len(v) for v in by_type.values()):  # round-robin over doc types
        for v in by_type.values():
            if i < len(v) and len(chosen) < n:
                chosen.append(v[i])
        i += 1
    pending = ROOT / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    for r in chosen:
        name = r["id"].replace("/", "__").replace("#", "_p")
        header = (f"---\ndoc_type: {r['meta'].get('doc_type', 'ris')}\njurisdiction: AT\nlang: {r['lang']}\n"
                  f"origin: {r['id']}\nreview: none\n---\n")
        (pending / f"{name}.md").write_text(header + to_tagged(r) + "\n", encoding="utf-8")
    ids = sorted({r["doc_id"] for r in chosen})
    with (ROOT / "doc_ids.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(ids) + "\n")
    print(f"{len(chosen)} paragraphs from {len(ids)} documents, {len(by_type)} doc types -> {pending}")


def export(out="data/canonical/gold_at.jsonl"):
    from legalner.tagged import parse_file
    files = sorted((ROOT / "reviewed").glob("*.md"))
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for f in files:
            recs, warnings = parse_file(f, "gold_at", max_chars=0)
            if warnings:
                raise SystemExit("\n".join(warnings))
            meta = f.read_text(encoding="utf-8").split("---\n")[1]
            review = next((ln.split(":", 1)[1].strip() for ln in meta.splitlines() if ln.startswith("review:")), "")
            for r in recs:
                r["meta"]["review"] = review
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} gold records -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("data", nargs="+")
    s.add_argument("--n", type=int, default=400)
    s.add_argument("--seed", type=int, default=7)
    sub.add_parser("export")
    args = ap.parse_args(argv)
    if args.cmd == "select":
        select(args.data, args.n, args.seed)
    else:
        export()


if __name__ == "__main__":
    main()
