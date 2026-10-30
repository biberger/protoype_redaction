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
    rf"(?:1er|[0-3]?\d)\s(?:{MONTHS_FR})\s(?:19|20)\d\d|(?:19|20)\d\d-[01]\d-[0-3]\d|"
    r"[0-3]\d/[01]\d/(?:19|20)\d\d)(?![\w/-])")
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


# a place inside the name of a unit is not a location (gold-set decision 7): "Regionaldirektion Steiermark"
UNIT_BEFORE = re.compile(r"(?:Regionaldirektion|Außenstelle|Landesstelle|Zweigstelle|Dienststelle|Werk(?:es|s)?|\w*[Zz]entrum|"
                         r"Filiale|Niederlassung|Standort)\s$")


DATELINE = re.compile(r"(?m)^([A-ZÄÖÜ][\wäöüßéèô.\-]+(?:\s(?:an\sder|am|im|bei|ob\sder|sur|en)\s[A-ZÄÖÜ][\wäöüß.\-]+|"
                      r"\s[A-ZÄÖÜ][\wäöüß.\-]+)?),\s(?:am\s|den\s|le\s|im\s)?(?:\d{1,2}\.?\s?(?:\d{1,2}\.|[A-Za-zäéû]+)|\[\[date)")


DEGREE_BEFORE = re.compile(r"(?<![\w.])(?:Dr\.|Mag\.(?:a)?|MMag\.|DI|Dipl\.-Ing\.|Ing\.|Prof\.|DDr\.|Univ\.-Prof\.)\s$")
IBAN_TEXT = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
CONTACT = re.compile(r"(?i)(?:\b(?:tel|tél|telefon|téléphone|phone|fax|mobil|mobile|handy|portable)\b\.?:?\s*"
                     r"(?:\(\w+\)\s*)?)((?:\+|00)?\d[\d /().\-]{6,}\d)|([\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+)")


_FR_TOWNS = ("Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg", "Montpellier", "Bordeaux",
             "Lille", "Rennes", "Reims", "Le Havre", "Grenoble", "Dijon", "Angers", "Nîmes", "Alès", "Metz", "Tours",
             "Rouen", "Caen", "Brest", "Limoges", "Amiens", "Perpignan", "Besançon", "Orléans", "Mulhouse", "Avignon",
             "Bruxelles", "Liège", "Namur", "Charleroi", "Mons", "Luxembourg", "Esch-sur-Alzette", "Genève", "Lausanne",
             "Neuchâtel", "Fribourg", "Sion")


def _known_towns():
    """Municipality names (AT/DE/CH gazetteer, ≥ 5 letters) and larger French-speaking towns."""
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "gazetteers" / "municipalities.tsv"
    names = set(_FR_TOWNS)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            name = line.split("\t")[1]
            if len(name) >= 5 and name[0].isupper():
                names.add(name)
    return names


KNOWN_TOWNS = _known_towns()
TOWN_WORDS = {"Regen", "Weil", "Wesen", "Ende", "Laufen", "Ruhe", "Linden", "Kosten", "Zeitz", "Hausen"}  # also words
TOWN_AFTER = re.compile(r"(?<![\w\[|])(?:in|nach|aus|bei|à|de|d['’])\s?([A-ZÄÖÜÉÈ][\w\-ÄÖÜäöüéèêâîôûç]+(?:[\s\-](?:an|am|im|bei|ob|sur|en|le|la)[\s\-][A-ZÄÖÜ]?[\w\-äöüéè]+)?)")


def _caps_passage(text, m, n):
    """True if the match is written in ALL CAPS or all lower case, as in a letterhead or a quoted e-mail."""
    word = m.group()
    if word == word.upper() and word != n:
        return True
    start = max(text.rfind("\n", 0, m.start()) + 1, m.start() - 60)
    end = text.find("\n", m.end())
    window = text[start:min(end if end != -1 else len(text), m.end() + 60)]  # same line, ±60 characters
    return word == word.lower() and not re.search(r"[A-ZÄÖÜ]", window.replace(word, ""))


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
        town = re.search(r"\b\d{4,5}\s([A-ZÄÖÜ][\w.\-]+(?:\s(?:an\sder|am|im|bei|ob\sder)?\s?[A-ZÄÖÜ][\w.\-]+){0,3})$",
                         surface) if label == "address" else None
        if town and len(town.group(1)) >= 4:
            needles.add(town.group(1))  # the town of a tagged address, written alone elsewhere, is a location
        if label == "person":
            last = surface.split()[-1]
            if len(last) >= 4 and last[0].isupper() and "*" not in last:
                needles.add(last)
    warnings = []
    for n in sorted(needles):
        for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?:s|')?(?!\w)", text, re.I):  # incl. genitive
            # "tribunal d'arrondissement …" for a tagged "Tribunal …" (names of several words only)
            same_but_first = " " in n and m.group()[1:len(n)] == n[1:]
            if m.group()[:len(n)] != n and not same_but_first and not _caps_passage(text, m, n):
                continue  # other case only inside ALL-CAPS or all-lower-case passages ("HUBER BAU GMBH", "t. bohush")
            if not any(covered[m.start():m.end()]) and not UNIT_BEFORE.search(text, 0, m.start()):
                line = text.count("\n", 0, m.start()) + 1
                warnings.append(f"{fname}:{line}: untagged occurrence of {n!r}")
    for m in IBAN_TEXT.finditer(text):
        if not any(covered[m.start():m.end()]) and m.group()[:2] in ("AT", "DE", "CH", "LI", "FR", "BE", "LU", "IT", "NL"):
            line = text.count("\n", 0, m.start()) + 1
            warnings.append(f"{fname}:{line}: untagged IBAN {m.group()!r}")
    for label, s, e, surface in spans:  # "Mag. [[judge|Heider]]": the degree belongs inside the span
        if label in ("person", "judge", "lawyer") and DEGREE_BEFORE.search(text, max(0, s - 25), s):
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: degree outside {label} span {surface!r}")
    for label, s, e, surface in spans:  # "FN [[company_register_number|531927x]]": the prefix belongs inside
        if label == "company_register_number" and re.search(r"(?<![\w.])(?:FN|HRB|HRA)\s$", text[max(0, s - 5):s]):
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: register prefix outside span {surface!r}")
    for m in CONTACT.finditer(text):
        g = 1 if m.group(1) else 2
        if not any(covered[m.start(g):m.end(g)]):
            line = text.count("\n", 0, m.start()) + 1
            warnings.append(f"{fname}:{line}: untagged {'phone number' if g == 1 else 'e-mail'} {m.group(g)!r}")
    for m in TOWN_AFTER.finditer(text):
        name = m.group(1)
        while name not in KNOWN_TOWNS and " " in name:
            name = name.rsplit(" ", 1)[0]
        s = m.start(1)
        if name in KNOWN_TOWNS and name not in TOWN_WORDS and not any(covered[s:s + len(name)]):
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: untagged place {name!r}")
    for m in DATELINE.finditer(text):
        if not any(covered[m.start(1):m.end(1)]) and not re.search(r"(?:ung|gericht|amt|stelle|ware|Datum|Ort)$",
                                                                       m.group(1)):
            line = text.count("\n", 0, m.start()) + 1
            warnings.append(f"{fname}:{line}: untagged place in dateline {m.group(1)!r}")
    for m in DATE_RE.finditer(text):
        if not any(covered[m.start():m.end()]):
            line = text.count("\n", 0, m.start()) + 1
            warnings.append(f"{fname}:{line}: untagged date {m.group()!r}")
    for label, s, e, surface in spans:
        if re.match(r"(?i)^(l['’]|le |la |les |das |der |die |dem |den |des )", surface) and \
                label == "legal_norm":
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: article inside {label} span {surface!r}")
    for label, s, e, surface in spans:
        first = surface.split()[0] if " " in surface else ""
        if re.fullmatch(r"[A-Z]{2,6}", first) and re.search(r"(?<!\w)" + re.escape(first) + r"[ \t]*$", text[max(0, s - len(first) - 2):s]):
            line = text.count("\n", 0, s) + 1
            warnings.append(f"{fname}:{line}: {first!r} repeated before span {surface!r}")
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


RANGE_GAP = re.compile(r"\s?(?:bis(?:\s(?:zum|zur|einschließlich|inklusive))?|-|–|au|jusqu['’]au)\s?")


def merge_date_ranges(text, spans):
    """Gold-set decision 8: "[[date|1.3.2025]] bis [[date|31.3.2025]]" is one date span."""
    dates = sorted((sp for sp in spans if sp[0] == "date"), key=lambda sp: sp[1])
    merged, drop = [], set()
    i = 0
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


def parse_file(path, source, max_chars=MAX_CHARS):
    """Parse one tagged file into (records, lint_warnings)."""
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
