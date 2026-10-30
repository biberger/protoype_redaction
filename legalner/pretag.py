"""Pre-annotate unlabelled chunks with a model and write inline-tagged documents for agent correction.

One file per document (chunks separated by a blank line), in the `[[label|surface]]` format of
data/synthetic/GENERATION.md, so the corrected files go through `legalner.tagged --strict` like synthetic data.
Overlapping predictions are resolved greedily: a role label (judge, lawyer) wins over person on the same span,
otherwise the longer span wins.

    python -m legalner.pretag out/v1/best data/eurlex/chunks.jsonl --source eurlex -o data/eurlex/pretagged
    python -m legalner.pretag --check data/eurlex/chunks.jsonl data/eurlex/corrected   # text unchanged by correction
"""
import argparse
import collections
import json
import pathlib
import re

from legalner.evaluate import ROLE_LABELS, predict

PRIORITY = {lab: 1 for lab in ROLE_LABELS}


def inline(text, pred):
    """Text with non-overlapping predicted spans written as [[label|surface]]."""
    cands = sorted(((s, e, lab) for lab, spans in pred.items() for s, e in spans),
                   key=lambda x: (-(x[1] - x[0]), -PRIORITY.get(x[2], 0), x[0]))
    chosen = []
    for s, e, lab in cands:
        surface = text[s:e]
        if surface != surface.strip() or "\n" in surface or "[" in surface or "]" in surface or "|" in surface:
            continue
        if all(e <= s2 or e2 <= s for s2, e2, _ in chosen):
            chosen.append((s, e, lab))
    out, pos = [], 0
    for s, e, lab in sorted(chosen):
        out.append(text[pos:s] + f"[[{lab}|{text[s:e]}]]")
        pos = e
    return "".join(out) + text[pos:]


def check(chunks_path, folder):
    """Every corrected file must carry exactly the original text once its tags are stripped. Returns problems."""
    from legalner.tagged import TAG_RE
    by_doc = collections.defaultdict(list)
    for ln in open(chunks_path, encoding="utf-8"):
        c = json.loads(ln)
        by_doc["EU_" + re.sub(r"\W+", "_", c["doc_id"].split("/", 1)[-1])].append(c["text"])
    problems = []
    for path in sorted(pathlib.Path(folder).rglob("*.md")):
        if path.stem not in by_doc:
            problems.append(f"{path}: unknown document")
            continue
        body = path.read_text(encoding="utf-8").split("---\n", 2)[-1].rstrip("\n")
        plain = TAG_RE.sub(lambda m: m.group(2), body)
        want = "\n\n".join(by_doc[path.stem])
        if plain != want:
            i = next((k for k, (a, b) in enumerate(zip(plain, want)) if a != b), min(len(plain), len(want)))
            problems.append(f"{path.name}: text changed at char {i}: {plain[max(0, i - 30):i + 30]!r} "
                            f"!= {want[max(0, i - 30):i + 30]!r}")
    return problems


def main(argv=None):
    import sys
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--check":
        problems = check(argv[1], argv[2])
        print("\n".join(problems) or "ok: text unchanged in every file")
        raise SystemExit(1 if problems else 0)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("chunks", help="JSONL with id, doc_id, lang, text (e.g. legalner.sources.eurlex chunks)")
    ap.add_argument("--source", required=True, help="schema source whose coverage decides the queried labels")
    ap.add_argument("--doc-type", default=None, help="front-matter doc_type (default: the chunk's 'type' field)")
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--device", default=None)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    import torch
    from gliner2 import AutoExtractor
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoExtractor.from_pretrained(args.model, map_location=device)
    model.eval()
    chunks = [dict(json.loads(ln), source=args.source, spans=[]) for ln in open(args.chunks, encoding="utf-8")]
    with torch.inference_mode():
        preds = predict(model, chunks, args.threshold, 8)
    by_doc = collections.defaultdict(list)
    for c, p in zip(chunks, preds):
        by_doc[c["doc_id"]].append(inline(c["text"], p))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {c["doc_id"]: c for c in chunks}
    for doc_id, parts in by_doc.items():
        c = meta[doc_id]
        name = "EU_" + re.sub(r"\W+", "_", doc_id.split("/", 1)[-1])
        doc_type = args.doc_type or f"{args.source}_{c.get('type', 'text')}"
        body = "\n\n".join(parts)
        (out / f"{name}.md").write_text(
            f"---\ndoc_type: {doc_type}\njurisdiction: EU\nlang: {c['lang']}\n---\n{body}\n", encoding="utf-8")
    print(f"{len(chunks)} chunks in {len(by_doc)} documents -> {out}")


if __name__ == "__main__":
    main()
