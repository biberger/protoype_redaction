"""Parse inline-tagged documents into canonical records.

Document format (one .md file per document):

    ---
    doc_type: ogh_urteil
    jurisdiction: AT
    lang: de
    ---
    Die klagende Partei [[person|Mag. Johanna Steinberger]], vertreten durch
    [[lawyer|Dr. Paul Huber]], ...

Tags are ``[[label|surface]]`` without nesting. `judge` and `lawyer` tags also
emit a `person` span. Files from the first synthetic batch (schema v1, upper
case German labels) are mapped onto the canonical schema; KENNNUMMER and
KONTAKT are split into fine identifier labels by pattern.

    python -m legalner.tagged data/synthetic/raw_v2 -o data/canonical/synthetic.jsonl --strict
"""
import argparse
import collections
import json
import pathlib
import re
import sys

from legalner.acts import act_names, find_untagged, find_untagged_citations
from legalner.schema import LABELS

MAX_CHARS = 1500
JURISDICTIONS = {"AT", "DE", "CH", "FR", "BE", "LU", "LI", "EU"}
ROLE_LABELS = {"judge", "lawyer"}

V1_LABELS = {
    "PERSON": "person", "ORGANISATION": "organization", "GERICHT": "court",
    "ADRESSE": "address", "ORT": "location", "DATUM": "date",
    "GESCHAEFTSZAHL": "case_number", "GESETZ": "legal_norm",
    "KENNNUMMER": None, "KONTAKT": None,  # resolved by v1_identifier_label
}

# frequent place names that should never appear untagged (lint only)
GAZETTEER = {
    "Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt", "Villach",
    "Wels", "Steyr", "St. Pölten", "Dornbirn", "Bregenz", "Feldkirch", "Leoben",
    "Eisenstadt", "Krems", "Mödling", "Berlin", "München", "Hamburg", "Köln",
    "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig", "Dresden", "Karlsruhe",
    "Hannover", "Nürnberg", "Bremen", "Erfurt", "Zürich", "Bern", "Basel",
    "Genf", "Genève", "Lausanne", "Luzern", "St. Gallen", "Paris", "Lyon",
    "Marseille", "Strasbourg", "Bordeaux", "Lille", "Toulouse", "Nantes",
    "Bruxelles", "Luxembourg", "Vaduz", "Österreich", "Deutschland", "Schweiz",
    "France", "Frankreich",
    # top courts: full names are often written untagged next to a tagged abbreviation
    "Verfassungsgerichtshof", "Verfassungsgerichtshofes", "Verfassungsgerichtshofs",
    "Verwaltungsgerichtshof", "Verwaltungsgerichtshofes", "Verwaltungsgerichtshofs",
    "Oberste Gerichtshof", "Obersten Gerichtshof", "Obersten Gerichtshofes", "Obersten Gerichtshofs",
    "Bundesverwaltungsgericht", "Bundesverwaltungsgerichtes", "Bundesverwaltungsgerichts",
    "Bundesgerichtshof", "Bundesgerichtshofes", "Bundesgerichtshofs", "Bundesverfassungsgericht",
    "Bundesverfassungsgerichts", "Bundesarbeitsgericht", "Bundesarbeitsgerichts", "Bundessozialgericht",
    "Bundesfinanzhof", "Bundesgericht", "Bundesgerichts", "Tribunal fédéral", "Cour de cassation",
    "Conseil d'État", "Conseil constitutionnel", "Cour constitutionnelle",
}

MONTHS_DE = "Jänner|Januar|Februar|Feber|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
MONTHS_FR = "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
DATE_RE = re.compile(
    rf"(?<![\w./-])(?:[0-3]?\d\.\s?[01]?\d\.\s?(?:19|20)\d\d|[0-3]?\d\.\s(?:{MONTHS_DE})\s(?:19|20)\d\d|"
    rf"(?:1er|[0-3]?\d)\s(?:{MONTHS_FR})\s(?:19|20)\d\d|(?:19|20)\d\d-[01]\d-[0-3]\d)(?![\w/-])")
TAG_RE = re.compile(r"\[\[([A-Za-z_]+)\|([^\[\]|]+?)\]\]")
HEADER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)

IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[\dA-Z ]{10,30}$")
BIC_RE = re.compile(r"^[A-Z]{6}[A-Z\d]{2}([A-Z\d]{3})?$")


class TagError(Exception):
    pass


CONTEXT_RULES = [  # (pattern on the ~60 chars before the span, label)
    (r"(?i)(personalausweis|ausweis|reisepass|führerschein|passport)", "id_document_number"),
    (r"(?i)(steuernummer|ust-?idnr|\buid\b)", "tax_id"),
    (r"(?i)(\bvnr\b|sv-nummer|sozialversicherungs)", "social_security_number"),
    (r"(?i)(\biban\b|kontonummer|\bkonto\b)", "bank_account"),
    (r"(?i)(katastralgemeinde|grundbuch|grundstück|\bgst\b|\bez\b|einlagezahl|flurstück)", "land_register_id"),
]


def v1_identifier_label(tag, surface, context=""):
    """Map a v1 KENNNUMMER/KONTAKT surface onto a fine canonical label, using
    the surface pattern and keywords in the preceding context."""
    s = surface.strip()
    compact = re.sub(r"\s", "", s)
    if tag == "KENNNUMMER":
        for pattern, label in CONTEXT_RULES:
            if re.search(pattern, context[-60:]):
                return label
        if re.match(r"^(Nr\. )?\d+/\d+$", s):
            return "land_register_id"
    if tag == "KONTAKT":
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", s):
            return "email"
        if sum(c.isdigit() for c in s) >= 6:
            return "phone_number"
        return "other_identifier"
    if IBAN_RE.match(compact) or BIC_RE.match(compact) or re.search(r"(?i)\b(iban|bic|konto)", s):
        return "bank_account"
    if re.match(r"(?i)^(FN|HRB|HRA|CHE-)", s):
        return "company_register_number"
    if re.match(r"(?i)^(ATU|DE\d{9}$|UID|St\.?-?Nr|Steuer)", s) or re.match(r"^\d{2}[ -]?\d{3}/\d{4}$", s):
        return "tax_id"
    if re.match(r"(?i)^(EZ|KG|GSt|Gst|Grundst|Flur|Einlage)", s) or re.search(r"(?i)\bKG\b|\bEZ\b", s):
        return "land_register_id"
    if re.match(r"^\d{4} ?\d{6}$", s) or re.match(r"^\d{4} \d{2}\d{2}\d{2}$", s):
        return "social_security_number"
    if re.match(r"^[A-ZÄÖÜ]{1,3}[ -]\d{1,5}[ -]?[A-Z]{0,3}$", s) or re.match(r"^[A-ZÄÖÜ]{1,3}-[A-Z]{1,2} ?\d{1,4}[EH]?$", s):
        return "license_plate"
    return "other_identifier"


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
        raise TagError(f"{fname}: unknown jurisdiction {meta['jurisdiction']!r}")
    meta.setdefault("lang", "de")
    return meta, raw[m.end():]


def resolve_label(tag, surface, fname, line, context=""):
    """Return the canonical labels a tag emits (role tags also emit person)."""
    if tag in V1_LABELS:
        label = V1_LABELS[tag] or v1_identifier_label(tag, surface, context)
        return [label]
    if tag not in LABELS:
        raise TagError(f"{fname}:{line}: unknown label {tag!r}")
    return [tag, "person"] if tag in ROLE_LABELS else [tag]


def strip_tags(body, fname):
    """Return (plain_text, [(label, start, end, surface), ...])."""
    out, spans, pos, cur = [], [], 0, 0
    for m in TAG_RE.finditer(body):
        out.append(body[pos:m.start()])
        cur += m.start() - pos
        tag, surface = m.group(1), m.group(2)
        line = body.count("\n", 0, m.start()) + 1
        if surface != surface.strip() or "\n\n" in surface:
            raise TagError(f"{fname}:{line}: bad whitespace in {surface!r}")
        context = "".join(out)[-60:]
        for label in resolve_label(tag, surface, fname, line, context):
            spans.append((label, cur, cur + len(surface), surface))
        out.append(surface)
        cur += len(surface)
        pos = m.end()
    out.append(body[pos:])
    text = "".join(out)
    for bad in ("[[", "]]"):
        idx = text.find(bad)
        if idx != -1:
            line = text.count("\n", 0, idx) + 1
            raise TagError(f"{fname}: malformed tag near plain-text line {line}: "
                           f"{text[max(0, idx - 40):idx + 60]!r}")
    return text, spans


def split_long(text, start, end, max_chars, spans):
    """Split an over-long paragraph at line breaks outside entity spans."""
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
    """Split on blank lines into chunks <= max_chars; returns [(text, spans)]."""
    paras = []
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


def lint(text, spans, fname):
    """Warn about untagged occurrences of strings tagged elsewhere in the doc
    (incl. bare surnames of person spans and common place names)."""
    covered = [False] * len(text)
    for _, s, e, _ in spans:
        for i in range(s, e):
            covered[i] = True
    needles = set(GAZETTEER)
    for label, _, _, surface in spans:
        if label in ("date", "legal_norm"):
            continue  # short forms legitimately repeat untagged
        needles.add(surface)
        if label == "person":
            last = surface.split()[-1]
            if len(last) >= 4 and last[0].isupper() and "*" not in last:
                needles.add(last)
    warnings = []
    for n in sorted(needles):
        for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?:s|')?(?!\w)", text):  # incl. genitive
            if not any(covered[m.start():m.end()]):
                line = text.count("\n", 0, m.start()) + 1
                warnings.append(f"{fname}:{line}: untagged occurrence of {n!r}")
    for m in DATE_RE.finditer(text):
        if not any(covered[m.start():m.end()]):
            line = text.count("\n", 0, m.start()) + 1
            warnings.append(f"{fname}:{line}: untagged date {m.group()!r}")
    for label, s, e, surface in spans:
        if re.match(r"(?i)^(l['’]|le |la |les |das |der |die |dem |den |des )", surface) and \
                label == "legal_norm":
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: article inside {label} span {surface!r}")
    acts = act_names(surface for label, _, _, surface in spans if label == "legal_norm")
    for s, e, name in find_untagged(text, covered, acts):
        line = text.count("\n", 0, s) + 1
        warnings.append(f"{fname}:{line}: untagged legal act {text[s:e]!r} (tag as legal_norm)")
        for i in range(s, e):
            covered[i] = True
    for s, e in find_untagged_citations(text, covered):
        line = text.count("\n", 0, s) + 1
        warnings.append(f"{fname}:{line}: untagged norm citation {text[s:e]!r}")
    return warnings


def parse_file(path, source, max_chars=MAX_CHARS):
    """Parse one tagged file into (records, lint_warnings)."""
    meta, body = parse_header(path.read_text(encoding="utf-8"), path.name)
    text, spans = strip_tags(body.lstrip("\n"), path.name)
    text = text.rstrip()
    warnings = lint(text, spans, path.name)
    parts = [(text, spans)] if not max_chars else chunk(text, spans, max_chars)
    records = []
    for i, (ctext, cspans) in enumerate(parts):
        rec_spans = []
        for label, s, e, surface in cspans:
            assert ctext[s:e] == surface, (path.name, label, s, e)
            rec_spans.append({"label": label, "start": s, "end": e, "text": surface})
        records.append({
            "id": f"{source}/{path.stem}#{i}", "source": source, "doc_id": path.stem,
            "lang": meta["lang"], "jurisdiction": meta["jurisdiction"],
            "text": ctext, "spans": rec_spans, "meta": {"doc_type": meta["doc_type"]},
        })
    return records, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="+", help="directories with tagged .md files (searched recursively)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--source", default="synthetic", help="source name (see schema.SOURCES)")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS, help="0 = one record per document")
    ap.add_argument("--strict", action="store_true", help="fail on lint warnings")
    args = ap.parse_args(argv)

    files = sorted(f for d in args.raw for f in pathlib.Path(d).rglob("*.md")
                   if f.name.lower() != "readme.md")
    if not files:
        sys.exit(f"no .md files in {args.raw}")
    counts, juris, langs = collections.Counter(), collections.Counter(), collections.Counter()
    records, warnings, errors = [], [], []
    for f in files:
        try:
            recs, warns = parse_file(f, args.source, args.max_chars)
        except TagError as e:
            errors.append(str(e))
            continue
        records += recs
        warnings += warns
        juris[recs[0]["jurisdiction"]] += 1
        langs[recs[0]["lang"]] += 1
        counts.update(s["label"] for r in recs for s in r["spans"])
    if errors:
        print("ERRORS:", *errors, sep="\n  ", file=sys.stderr)
        sys.exit(1)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"documents: {len(files)}  records: {len(records)}  -> {out}")
    print("jurisdiction:", dict(sorted(juris.items())), " lang:", dict(sorted(langs.items())))
    for label, n in counts.most_common():
        print(f"  {label:24s} {n:6d}")
    if warnings:
        print(f"\nlint warnings ({len(warnings)}):", *warnings, sep="\n  ")
        if args.strict:
            sys.exit(2)


if __name__ == "__main__":
    main()
