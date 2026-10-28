#!/usr/bin/env python3
"""Convert tagged synthetic legal documents (raw/*.md) into NER JSONL.

Input format (one file per document):

    ---
    doc_type: ogh_urteil
    jurisdiction: AT
    ---
    Die klagende Partei [[PERSON|Mag. Johanna Steinberger]], wohnhaft in ...

Tags are ``[[LABEL|surface text]]``; no nesting. The header block is removed.
Output: one JSON object per chunk (paragraphs joined greedily up to
MAX_CHARS, split on blank lines), offsets relative to the chunk text.

Usage:
    python3 tools/convert.py                 # raw/ -> synthetic.jsonl
    python3 tools/convert.py --strict        # also fail on lint warnings
    python3 tools/convert.py --no-chunk      # one line per document
Stdlib only.
"""
import argparse
import collections
import json
import pathlib
import re
import sys

LABELS = [
    "PERSON", "ORGANISATION", "GERICHT", "ADRESSE", "ORT", "DATUM",
    "GESCHAEFTSZAHL", "GESETZ", "KENNNUMMER", "KONTAKT",
]
JURISDICTIONS = {"AT", "DE"}
MAX_CHARS = 1500

# frequent place names that should never appear untagged (lint only)
GAZETTEER = {
    "Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt", "Villach",
    "Wels", "Steyr", "St. Pölten", "Dornbirn", "Bregenz", "Feldkirch",
    "Leoben", "Eisenstadt", "Krems", "Mödling", "Berlin", "München",
    "Hamburg", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig",
    "Dresden", "Karlsruhe", "Hannover", "Nürnberg", "Bremen", "Erfurt",
    "Österreich", "Deutschland",
}

BASE = pathlib.Path(__file__).resolve().parent.parent
TAG_RE = re.compile(r"\[\[([A-Z]+)\|([^\[\]|]+?)\]\]")
HEADER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


class TagError(Exception):
    pass


def parse_header(raw, fname):
    m = HEADER_RE.match(raw)
    if not m:
        raise TagError(f"{fname}: missing '---' header block")
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, val = line.partition(":")
        if not sep:
            raise TagError(f"{fname}: bad header line {line!r}")
        meta[key.strip()] = val.strip()
    for key in ("doc_type", "jurisdiction"):
        if not meta.get(key):
            raise TagError(f"{fname}: header lacks {key}")
    if meta["jurisdiction"] not in JURISDICTIONS:
        raise TagError(f"{fname}: jurisdiction must be AT or DE")
    return meta, raw[m.end():]


def strip_tags(body, fname):
    """Return (plain_text, [(label, start, end, surface), ...])."""
    out, spans, pos, cur = [], [], 0, 0
    for m in TAG_RE.finditer(body):
        out.append(body[pos:m.start()])
        cur += m.start() - pos
        label, surface = m.group(1), m.group(2)
        line = body.count("\n", 0, m.start()) + 1
        if label not in LABELS:
            raise TagError(f"{fname}:{line}: unknown label {label!r}")
        if surface != surface.strip() or "\n\n" in surface:
            raise TagError(f"{fname}:{line}: bad whitespace in {surface!r}")
        out.append(surface)
        spans.append((label, cur, cur + len(surface), surface))
        cur += len(surface)
        pos = m.end()
    out.append(body[pos:])
    text = "".join(out)
    # anything tag-like left over is malformed
    for bad in ("[[", "]]"):
        idx = text.find(bad)
        if idx != -1:
            line = text.count("\n", 0, idx) + 1
            raise TagError(f"{fname}: malformed tag near plain-text line {line}: "
                           f"{text[max(0, idx - 40):idx + 60]!r}")
    return text, spans


def split_long(text, start, end, max_chars, spans):
    """Split an over-long paragraph (e.g. a register extract without blank
    lines) at line breaks that do not fall inside an entity span."""
    if end - start <= max_chars:
        return [(start, end)]
    inside = {i for _, s, e, _ in spans for i in range(s, e)}
    cuts = [i for i in range(start, end) if text[i] == "\n" and i not in inside]
    pieces, cur = [], start
    for i, c in enumerate(cuts):
        nxt = cuts[i + 1] if i + 1 < len(cuts) else end
        if nxt - cur > max_chars and c > cur:
            pieces.append((cur, c))
            cur = c + 1
    pieces.append((cur, end))
    return pieces


def chunk(text, spans, max_chars):
    """Split text on blank lines into chunks <= max_chars (a single longer
    paragraph becomes its own chunk). Returns [(chunk_text, chunk_spans)]."""
    paras = []  # (start, end) of non-blank paragraphs
    for m in re.finditer(r"\S(?:.*?\S)?(?=\n[ \t]*\n|\s*\Z)", text, re.S):
        paras.extend(split_long(text, m.start(), m.end(), max_chars, spans))
    groups, cur = [], None
    for s, e in paras:
        if cur and e - cur[0] <= max_chars:
            cur[1] = e
        else:
            if cur:
                groups.append(cur)
            cur = [s, e]
    if cur:
        groups.append(cur)
    result = []
    for gs, ge in groups:
        cspans = []
        for label, s, e, surface in spans:
            if s >= gs and e <= ge:
                cspans.append((label, s - gs, e - gs, surface))
            elif s < ge and e > gs:
                raise TagError(f"span {surface!r} crosses chunk boundary")
        result.append((text[gs:ge], cspans))
    return result


def make_record(text, spans, meta, fname):
    ents = {lab: [] for lab in LABELS}
    for label, s, e, surface in spans:
        assert text[s:e] == surface, (fname, label, s, e, text[s:e], surface)
        ents[label].append({"text": surface, "start": s, "end": e})
    return {"text": text, "entities": ents,
            "meta": {"source_file": fname, "doc_type": meta["doc_type"],
                     "jurisdiction": meta["jurisdiction"]}}


def lint(text, spans, fname):
    """Warn about untagged occurrences of strings tagged elsewhere in the doc
    (incl. the last token of PERSON spans, i.e. bare surnames)."""
    covered = [False] * len(text)
    for _, s, e, _ in spans:
        for i in range(s, e):
            covered[i] = True
    needles = set()
    for label, _, _, surface in spans:
        if label in ("DATUM", "GESETZ"):
            continue  # too generic / short forms legitimately repeat
        needles.add(surface)
        if label == "PERSON":
            last = surface.split()[-1]
            if len(last) >= 4 and last[0].isupper():
                needles.add(last)
    needles.update(GAZETTEER)
    warnings = []
    for n in sorted(needles):
        for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text):
            if not any(covered[m.start():m.end()]):
                line = text.count("\n", 0, m.start()) + 1
                warnings.append(f"{fname}:{line}: untagged occurrence of {n!r}")
    return warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(BASE / "raw"))
    ap.add_argument("--out", default=str(BASE / "synthetic.jsonl"))
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    ap.add_argument("--no-chunk", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on lint warnings")
    args = ap.parse_args()

    files = sorted(pathlib.Path(args.raw).glob("*.md"))
    if not files:
        sys.exit(f"no .md files in {args.raw}")
    counts = collections.Counter()
    juris = collections.Counter()
    doc_types = collections.Counter()
    n_chunks, warnings, errors = 0, [], []
    records = []
    for f in files:
        try:
            meta, body = parse_header(f.read_text(encoding="utf-8"), f.name)
            text, spans = strip_tags(body.lstrip("\n"), f.name)
            text = text.rstrip()
            warnings += lint(text, spans, f.name)
            parts = [(text, spans)] if args.no_chunk else chunk(text, spans, args.max_chars)
            for ctext, cspans in parts:
                records.append(make_record(ctext, cspans, meta, f.name))
                for label, *_ in cspans:
                    counts[label] += 1
            n_chunks += len(parts)
            juris[meta["jurisdiction"]] += 1
            doc_types[meta["doc_type"]] += 1
        except TagError as e:
            errors.append(str(e))
    if errors:
        print("ERRORS:", *errors, sep="\n  ", file=sys.stderr)
        sys.exit(1)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"documents: {len(files)}  chunks: {n_chunks}  -> {args.out}")
    print("jurisdiction:", dict(sorted(juris.items())))
    print("doc types:")
    for k, v in sorted(doc_types.items()):
        print(f"  {k:28s} {v}")
    print("entities per label:")
    for lab in LABELS:
        print(f"  {lab:15s} {counts[lab]:6d}")
    print(f"  {'TOTAL':15s} {sum(counts.values()):6d}")
    if warnings:
        print(f"\nlint warnings ({len(warnings)}):", *warnings, sep="\n  ")
        if args.strict:
            sys.exit(2)


if __name__ == "__main__":
    main()
