"""Validate inline-tagged synthetic OBDK documents and convert them to canonical JSONL.

    python check.py <raw_dir> [<raw_dir> ...] -o out.jsonl [--strict] [--max-chars 1500]

Same file format and canonical record layout as legalner.tagged (schema v2,
data/synthetic/GENERATION.md): ``[[label|surface]]`` tags, no nesting, judge and
lawyer tags also emit a person span, date ranges are merged. The lint is a port of
the legalner.tagged checks that matter here (untagged repeats and surnames, untagged
dates, IBANs, phone numbers, e-mails, norm citations, act names, degrees and register
prefixes outside spans) plus the check-digit checks of legalner.audit (IBAN, SV-Nummer,
FN, UID). --strict exits with 2 when there are lint warnings.
"""

import argparse
import collections
import json
import pathlib
import re
import sys

LABELS = {
    "person", "judge", "lawyer", "organization", "court", "address", "street", "location", "date",
    "case_number", "bank_account", "social_security_number", "tax_id", "company_register_number",
    "license_plate", "land_register_id", "id_document_number", "other_identifier", "phone_number",
    "email", "legal_norm",
}
ROLE_LABELS = {"judge", "lawyer"}
MAX_CHARS = 1500

TAG_RE = re.compile(r"\[\[([A-Za-z_]+)\|([^\[\]|]+?)\]\]")
HEADER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
MONTHS_DE = "Jänner|Januar|Februar|Feber|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
DATE_RE = re.compile(
    rf"(?<![\w./-])(?:[0-3]?\d\.\s?[01]?\d\.\s?(?:19|20)\d\d|[0-3]?\d\.\s(?:{MONTHS_DE})\s(?:19|20)\d\d|"
    r"(?:19|20)\d\d-[01]\d-[0-3]\d)(?![\w/-])")
IBAN_TEXT = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
CONTACT = re.compile(r"(?i)(?:\b(?:tel|telefon|fax|mobil|handy)\b\.?:?\s*(?:\(\w+\)\s*)?)((?:\+|00)?\d[\d /().\-]{6,}\d)"
                     r"|([\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+)")
DEGREE_BEFORE = re.compile(r"(?<![\w.])(?:Dr\.|Mag\.(?:a)?|MMag\.|DI|Dipl\.-Ing\.|Ing\.|Prof\.|DDr\.|Univ\.-Prof\.)\s$")
GAZETTEER = {
    "Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt", "Villach", "Wels", "Steyr", "St. Pölten",
    "Dornbirn", "Bregenz", "Feldkirch", "Leoben", "Eisenstadt", "Krems", "Mödling", "Österreich",
    "Verfassungsgerichtshof", "Verfassungsgerichtshofes", "Verwaltungsgerichtshof", "Verwaltungsgerichtshofes",
    "Oberste Gerichtshof", "Obersten Gerichtshof", "Obersten Gerichtshofes", "Obersten Gerichtshofs",
}
LONG_ACTS = (
    "Allgemeines bürgerliches Gesetzbuch", "Allgemeinen bürgerlichen Gesetzbuch", "Rechtsanwaltsordnung",
    "Disziplinarstatut", "Bundes-Verfassungsgesetz", "Strafgesetzbuch", "Strafprozessordnung",
    "Zivilprozessordnung", "Exekutionsordnung", "Konkursordnung", "Insolvenzordnung", "Notariatsordnung",
    "Europäische Menschenrechtskonvention", "Europäischen Menschenrechtskonvention", "EMRK",
    "Allgemeines Verwaltungsverfahrensgesetz", "Straßenverkehrsordnung", "Rechtsanwaltstarifgesetz",
)
CITATION_RE = re.compile(
    r"(?:§§?|Art\.|Art|Artikel)\s?\d[^\n()\[\];:]{0,50}?"
    r"(?<![\w\-])[A-ZÄÖÜ][A-Za-zÄÖÜäöü\-]*[A-ZÄÖÜ](?:\s(?:[IVX]+|\d{4}))?(?![\w\-])")
_DE_ACT = re.compile(r"([A-ZÄÖÜ][\w\-äöüÄÖÜ]*[A-ZÄÖÜ][\w\-äöüÄÖÜ]*(?:\s+(?:[IVX]+|\d{4}))?)$")
RANGE_GAP = re.compile(r"\s?(?:bis(?:\s(?:zum|zur|einschließlich))?|-|–)\s?")

SVNR_WEIGHTS = (3, 7, 9, 0, 5, 8, 4, 2, 1, 6)
FN_LETTERS = "abdfghikmpstvwxyz"
FN_WEIGHTS = (6, 4, 14, 15, 10, 1)


class TagError(Exception):
    pass


# ---------------------------------------------------------------- check digits (legalner.audit)
def iban_ok(v):
    s = v.replace(" ", "")
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return None  # not an IBAN (old account numbers are fine)
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def svnr_ok(v):
    s = v.replace(" ", "")
    if not re.fullmatch(r"\d{10}", s):
        return None
    d = [int(c) for c in s]
    return sum(w * x for w, x in zip(SVNR_WEIGHTS, d)) % 11 == d[3]


def fn_ok(v):
    m = re.fullmatch(r"FN\s*(\d{1,6})\s*([a-z])", v.strip())
    if not m:
        return None
    d = [int(c) for c in f"{int(m.group(1)):06d}"]
    return FN_LETTERS[sum(w * x for w, x in zip(FN_WEIGHTS, d)) % 17] == m.group(2)


def uid_ok(v):
    s = re.sub(r"\s", "", v).upper()
    if not re.fullmatch(r"ATU\d{8}", s):
        return None
    total = 0
    for i, c in enumerate(s[3:10]):
        x = int(c) * (2 if i % 2 else 1)
        total += x // 10 + x % 10
    return (96 - total) % 10 == int(s[10])


CHECKS = {"bank_account": iban_ok, "social_security_number": svnr_ok,
          "company_register_number": fn_ok, "tax_id": uid_ok}


# ---------------------------------------------------------------- parsing
def parse_header(raw, fname):
    m = HEADER_RE.match(raw)
    if not m:
        raise TagError(f"{fname}: missing '---' header block")
    meta = {}
    for line in m.group(1).splitlines():
        if line.strip():
            key, sep, val = line.partition(":")
            if not sep:
                raise TagError(f"{fname}: bad header line {line!r}")
            meta[key.strip()] = val.strip()
    for key in ("doc_type", "jurisdiction", "year"):
        if not meta.get(key):
            raise TagError(f"{fname}: header lacks {key}")
    meta.setdefault("lang", "de")
    return meta, raw[m.end():]


def strip_tags(body, fname):
    out, spans, pos, cur = [], [], 0, 0
    for m in TAG_RE.finditer(body):
        out.append(body[pos:m.start()])
        cur += m.start() - pos
        tag, surface = m.group(1), m.group(2)
        line = body.count("\n", 0, m.start()) + 1
        if tag not in LABELS:
            raise TagError(f"{fname}:{line}: unknown label {tag!r}")
        if surface != surface.strip() or "\n\n" in surface:
            raise TagError(f"{fname}:{line}: bad whitespace in {surface!r}")
        for label in ([tag, "person"] if tag in ROLE_LABELS else [tag]):
            spans.append((label, cur, cur + len(surface), surface))
        out.append(surface)
        cur += len(surface)
        pos = m.end()
    out.append(body[pos:])
    text = "".join(out)
    for bad in ("[[", "]]", "|]", "[|"):
        idx = text.find(bad)
        if idx != -1:
            line = text.count("\n", 0, idx) + 1
            raise TagError(f"{fname}: malformed tag near plain-text line {line}: {text[max(0, idx - 40):idx + 60]!r}")
    return text, spans


def merge_date_ranges(text, spans):
    dates = sorted((sp for sp in spans if sp[0] == "date"), key=lambda sp: sp[1])
    merged, drop, i = [], set(), 0
    while i < len(dates):
        label, s, e, _ = dates[i]
        j = i
        while j + 1 < len(dates) and RANGE_GAP.fullmatch(text[e:dates[j + 1][1]]):
            j += 1
            e = dates[j][2]
        if j > i:
            drop.update(dates[i:j + 1])
            merged.append((label, s, e, text[s:e]))
        i = j + 1
    if not merged:
        return spans
    return sorted([sp for sp in spans if sp not in drop] + merged, key=lambda sp: (sp[1], sp[0]))


def act_names(spans):
    names: set[str] = set(LONG_ACTS)
    for label, _, _, surface in spans:
        if label == "legal_norm":
            m = _DE_ACT.search(surface.strip().rstrip(".,;"))
            if m and m.group(1) != surface.strip() and len(m.group(1)) >= 2:
                names.add(m.group(1))
    return names


def lint(text, spans, fname):
    covered = [False] * len(text)
    for _, s, e, _ in spans:
        for i in range(s, e):
            covered[i] = True

    def warn(pos, msg):
        warnings.append(f"{fname}:{text.count(chr(10), 0, pos) + 1}: {msg}")

    warnings = []
    needles = set(GAZETTEER)
    for label, _, _, surface in spans:
        if label in ("date", "legal_norm"):
            continue
        needles.add(surface)
        if label == "person":
            last = surface.split()[-1]
            if len(last) >= 4 and last[0].isupper() and "*" not in last:
                needles.add(last)
    for n in sorted(needles):
        for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?:s|')?(?!\w)", text):
            if not any(covered[m.start():m.end()]):
                warn(m.start(), f"untagged occurrence of {n!r}")
    for m in IBAN_TEXT.finditer(text):
        if not any(covered[m.start():m.end()]) and m.group()[:2] in ("AT", "DE", "CH", "LI"):
            warn(m.start(), f"untagged IBAN {m.group()!r}")
    for m in CONTACT.finditer(text):
        g = 1 if m.group(1) else 2
        if not any(covered[m.start(g):m.end(g)]):
            warn(m.start(), f"untagged {'phone number' if g == 1 else 'e-mail'} {m.group(g)!r}")
    for m in DATE_RE.finditer(text):
        if not any(covered[m.start():m.end()]):
            warn(m.start(), f"untagged date {m.group()!r}")
    for label, s, e, surface in spans:
        if label in ("person", "judge", "lawyer") and DEGREE_BEFORE.search(text, max(0, s - 25), s):
            warn(s, f"degree outside {label} span {surface!r}")
        if label == "company_register_number" and re.search(r"(?<![\w.])(?:FN|HRB|HRA)\s$", text[max(0, s - 5):s]):
            warn(s, f"register prefix outside span {surface!r}")
        if label == "legal_norm" and re.match(r"(?i)^(das |der |die |dem |den |des )", surface):
            warn(s, f"article inside legal_norm span {surface!r}")
        check = CHECKS.get(label)
        if check and check(surface) is False:
            warn(s, f"wrong check digit in {label} {surface!r}")
    taken = list(covered)
    for name in sorted(act_names(spans), key=len, reverse=True):
        for m in re.finditer(r"(?<![\w\-/])" + re.escape(name) + r"(?![\w\-])", text):
            if not any(taken[m.start():m.end()]):
                warn(m.start(), f"untagged legal act {name!r} (tag the citation as legal_norm)")
                for i in range(m.start(), m.end()):
                    taken[i] = True
    for m in CITATION_RE.finditer(text):
        if not any(taken[m.start():m.end()]):
            warn(m.start(), f"untagged norm citation {m.group()!r}")
    return warnings


# ---------------------------------------------------------------- chunking (as legalner.tagged)
def split_long(text, start, end, max_chars, spans):
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


def parse_file(path, source, max_chars):
    meta, body = parse_header(path.read_text(encoding="utf-8"), path.name)
    text, spans = strip_tags(body.lstrip("\n"), path.name)
    text = text.rstrip()
    spans = merge_date_ranges(text, spans)
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
            "lang": meta["lang"], "jurisdiction": meta["jurisdiction"], "text": ctext, "spans": rec_spans,
            "meta": {"doc_type": meta["doc_type"], "year": int(meta["year"])},
        })
    return records, warnings


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252 console vs. names like ř
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--source", default="synthetic_obdk")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS, help="0 = one record per document")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    files = sorted(f for d in args.raw for f in pathlib.Path(d).rglob("*.md") if f.name.lower() != "readme.md")
    if not files:
        sys.exit(f"no .md files in {args.raw}")
    counts = collections.Counter()
    records, warnings, errors = [], [], []
    for f in files:
        try:
            recs, warns = parse_file(f, args.source, args.max_chars)
        except (TagError, AssertionError) as e:
            errors.append(str(e))
            continue
        records += recs
        warnings += warns
        counts.update(s["label"] for r in recs for s in r["spans"])
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    words = sum(len(r["text"].split()) for r in records)
    print(f"documents: {len(files) - len(errors)} ok, {len(errors)} with errors  records: {len(records)}  "
          f"words: {words}  -> {out}")
    for label, n in counts.most_common():
        print(f"  {label:24s} {n:6d}")
    if errors:
        print("\nERRORS:", *errors, sep="\n  ")
    if warnings:
        print(f"\nlint warnings ({len(warnings)}):", *warnings, sep="\n  ")
    if errors:
        sys.exit(1)
    if warnings and args.strict:
        sys.exit(2)


if __name__ == "__main__":
    main()
