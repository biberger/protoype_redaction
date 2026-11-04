"""Document-level post-processing for the anonymisation service: name propagation.

The service runs the model on short chunks, so a name found in the party block can be missed pages later. After all
chunks of a document are predicted, `propagate` masks every further occurrence of what was found anywhere in it:

- persons (person/judge/lawyer): the full name, and the surname alone (also in capitals and with a genitive -s),
  unless the surname is a common capitalised word (`common_capitalized.txt`: words that occur often in the corpora
  but rarely inside a person span, e.g. "Richter", "Partei", "Wien");
- organisations: the full name, the name without its legal form ("Huber Bau GmbH" -> "Huber Bau") and an abbreviation
  defined right after it ("Huber Bau GmbH (HBG)");
- identifiers (IBAN, file references, register numbers, plates, phone, e-mail, ...): exact repeats only.

Masks are (start, end, label) character spans; an occurrence that overlaps an existing mask is left alone.
"""
import pathlib
import re

COMMON = frozenset(pathlib.Path(__file__).with_name("common_capitalized.txt").read_text(encoding="utf-8").split())
NAME_LABELS = {"person", "judge", "lawyer"}
ORG_LABELS = {"organization"}
ID_LABELS = {"bank_account", "other_identifier", "case_number", "land_register_id", "company_register_number",
             "tax_id", "social_security_number", "license_plate", "id_document_number", "phone_number", "email"}
DEGREES = {"Dr", "Mag", "DI", "Ing", "Dipl", "MMag", "Prof", "Univ", "DDr", "Bakk", "BA", "MA", "MSc", "BSc", "LL",
           "MBA", "FH", "PhD", "Dkfm", "KR", "Hofrat", "HR", "Senatspräsident", "Präsident", "Präsidentin"}
LEGAL_FORM = re.compile(r"[\s,]*(?:GmbH\s*&\s*Co\.?\s*KG|Gesellschaft\s+m\.\s?b\.\s?H\.?|Ges\.?\s?m\.?\s?b\.?\s?H\.?|"
                        r"GmbH|AG|KG|OG|OHG|e\.\s?U\.|SE|eGen|eG|e\.\s?V\.|Privatstiftung|Stiftung|S\.A\.|SARL|"
                        r"S\.à\s?r\.l\.|Ltd\.?|Inc\.?|registrierte Genossenschaft.*)$")
ABBR_AFTER = re.compile(r"\s*\(\s*(?:im Folgenden:?\s*|kurz:?\s*)?[„\"]?([A-ZÄÖÜ][A-ZÄÖÜ0-9&\-]{1,9})[“\"]?\s*\)")
WORD = r"[0-9A-Za-zÄÖÜäöüßÀ-ÿ]"
TOKEN = re.compile(r"[A-ZÄÖÜ][a-zäöüßà-ÿ'\-]+(?:-[A-ZÄÖÜ][a-zäöüßà-ÿ]+)?")


def _surname(surface):
    """Last name token of a person span, without degrees; None if too short or a common word."""
    toks = [t for t in TOKEN.findall(surface) if t.rstrip(".") not in DEGREES]
    if len(toks) < 2:
        return None
    last = toks[-1]
    return last if len(last) >= 3 and last not in COMMON else None


def _org_core(surface):
    core = LEGAL_FORM.sub("", surface).strip(" ,")
    if core == surface or len(core) < 4:
        return None
    if " " not in core and core in COMMON:
        return None
    return core


def seeds(text, masks):
    """[(regex, label, rank)] for everything worth propagating from one text's masks.

    rank orders the alternatives: whole surfaces (longest first) before surnames alone."""
    out = []
    for s, e, lab in masks:
        surface = text[s:e].strip()
        if len(surface) < 3:
            continue
        flexible = r"\s+".join(re.escape(p) for p in surface.split())
        if lab in NAME_LABELS:
            out.append((flexible, lab, (0, -len(surface))))
            sur = _surname(surface)
            if sur:
                out.append((rf"(?:{re.escape(sur)}|{re.escape(sur.upper())})(?:s|')?", lab, (1, -len(sur))))
        elif lab in ORG_LABELS:
            out.append((flexible, lab, (0, -len(surface))))
            core = _org_core(surface)
            if core:
                out.append((r"\s+".join(re.escape(p) for p in core.split()), lab, (0, -len(core))))
            m = ABBR_AFTER.match(text, e)
            if m and m.group(1) not in COMMON:
                out.append((re.escape(m.group(1)), lab, (0, -len(m.group(1)))))
        elif lab in ID_LABELS:
            out.append((flexible, lab, (0, -len(surface))))
    return out


def propagate(texts, masks_list):
    """texts and masks of the records of one document -> masks with further occurrences added."""
    all_seeds, rank = {}, {}
    for text, masks in zip(texts, masks_list):
        for pat, lab, r in seeds(text, masks):
            all_seeds.setdefault(pat, lab)
            rank[pat] = min(rank.get(pat, r), r)
    if not all_seeds:
        return [list(m) for m in masks_list]
    # whole surfaces (longest first) before surnames alone, so "Huber Bau" wins over "Huber"
    pats = sorted(all_seeds, key=lambda p: rank[p])
    rx = re.compile(rf"(?<!{WORD})(?:" + "|".join(f"(?P<p{i}>{p})" for i, p in enumerate(pats)) + rf")(?!{WORD})")
    out = []
    for text, masks in zip(texts, masks_list):
        new = list(masks)
        taken = sorted((s, e) for s, e, _ in masks)
        for m in rx.finditer(text):
            s, e = m.span()
            if any(a < e and s < b for a, b in taken):
                continue
            lab = all_seeds[pats[int(m.lastgroup[1:])]]
            new.append((s, e, lab))
            taken.append((s, e))
        out.append(new)
    return out
