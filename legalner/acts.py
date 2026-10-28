"""Named legal acts (bare act names) for the legal_norm convention.

Convention (aligned with LER): a named statute, code, regulation or treaty is a
`legal_norm` even without § or Art. ("das [[legal_norm|ABGB]]", "le [[legal_norm|Code civil]]",
"die [[legal_norm|DSGVO]]"). Gazette references (BGBl., JO) are not.

`act_names(doc_spans)` returns the names to look for in one document: the act
part of every legal_norm span in the document plus the long-form names below.
Short abbreviations are only used when the document itself cites them with a
§/Art., so "OR" or "IO" are never matched in a document that does not cite them.
"""
import re

LONG_NAMES = (
    # AT
    "Allgemeines bürgerliches Gesetzbuch", "Allgemeinen bürgerlichen Gesetzbuch",
    "Allgemeinen bürgerlichen Gesetzbuches", "Bundes-Verfassungsgesetz", "Bundes-Verfassungsgesetzes",
    "Mietrechtsgesetz", "Mietrechtsgesetzes", "Konsumentenschutzgesetz", "Konsumentenschutzgesetzes",
    "Exekutionsordnung", "Insolvenzordnung", "Allgemeines Sozialversicherungsgesetz",
    "Allgemeinen Sozialversicherungsgesetzes", "Gewerbeordnung", "Wohnungseigentumsgesetz",
    "Unternehmensgesetzbuch", "Außerstreitgesetz", "Asylgesetz", "Fremdenpolizeigesetz",
    "Allgemeines Verwaltungsverfahrensgesetz", "Verwaltungsstrafgesetz", "Datenschutzgesetz",
    "Angestelltengesetz", "Bundesabgabenordnung", "Straßenverkehrsordnung",
    # DE
    "Grundgesetz", "Grundgesetzes", "Bürgerliches Gesetzbuch", "Bürgerlichen Gesetzbuch",
    "Bürgerlichen Gesetzbuches", "Zivilprozessordnung", "Strafgesetzbuch", "Strafgesetzbuches",
    "Strafprozessordnung", "Handelsgesetzbuch", "Abgabenordnung", "Sozialgesetzbuch",
    "Betriebsverfassungsgesetz", "Kündigungsschutzgesetz", "Baugesetzbuch",
    "Verwaltungsgerichtsordnung", "Gerichtsverfassungsgesetz",
    # CH
    "Obligationenrecht", "Obligationenrechts", "Zivilgesetzbuch", "Zivilgesetzbuches",
    "Bundesverfassung", "Bundesgerichtsgesetz", "Code des obligations", "Code civil suisse",
    # FR / BE / LU
    "Code civil", "code civil", "Code pénal", "code pénal", "Code du travail", "code du travail",
    "Code de procédure civile", "code de procédure civile", "Code de procédure pénale",
    "code de procédure pénale", "Code de commerce", "code de commerce", "Code de la consommation",
    "code de la consommation", "Code judiciaire", "Code de la route", "code de la route",
    "Code de droit économique",
    # EU / international
    "Datenschutz-Grundverordnung", "DSGVO", "RGPD", "EMRK", "CEDH",
    "Europäische Menschenrechtskonvention", "Europäischen Menschenrechtskonvention",
    "Convention européenne des droits de l'homme", "AEUV", "TFUE", "GRC",
)

_FR_ACT = re.compile(r"\b(?:du|de la|de l'|de l’|des)\s+((?:[Cc]ode|[Ll]oi|[Rr]èglement|[Dd]écret|[Cc]onvention)\b.*)$")
_DE_ACT = re.compile(r"([A-ZÄÖÜ][\w\-äöüÄÖÜ]*[A-ZÄÖÜ][\w\-äöüÄÖÜ]*(?:\s+(?:[IVX]+|\d{4}|ZH|BE|SH))?)$")
_ABBR_RE = re.compile(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöü\-]*[A-ZÄÖÜ]")


def act_of(norm):
    """Act part of a legal_norm surface ('§ 879 Abs 3 ABGB' -> 'ABGB'), or None."""
    norm = norm.strip().rstrip(".,;")
    m = _FR_ACT.search(norm)
    if m:
        return m.group(1)
    m = _DE_ACT.search(norm)
    if m and m.group(1) != norm and _ABBR_RE.match(m.group(1)):
        return m.group(1)
    return None


def act_names(norm_surfaces):
    names = set(LONG_NAMES)
    for n in norm_surfaces:
        a = act_of(n)
        if a and len(a) >= 2:
            names.add(a)
    return names


_CITE_START = re.compile(r"(?:§§?|Art\.|Art|art\.|Artikel|[Aa]rticles?)\s[^\n()\[\];]*$")
_YEAR = re.compile(r"\s\d{4}(?!\d)")


def extend(text, s, e, taken):
    """Grow an act-name match to the full citation: back to a preceding '§'/'Art.'
    on the same clause, forward over a year suffix ('StVO 1960')."""
    m = _CITE_START.search(text, max(0, s - 80), s)
    if m and not any(taken[m.start():s]):
        s = m.start()
    y = _YEAR.match(text, e)
    if y and not any(taken[e:y.end()]):
        e = y.end()
    return s, e


def find_untagged(text, covered, names):
    """[(start, end, name)] for untagged occurrences of act names (extended to
    the whole citation), longest name first."""
    hits = []
    taken = list(covered)
    for name in sorted(names, key=len, reverse=True):
        for m in re.finditer(r"(?<![\w\-/])" + re.escape(name) + r"(?![\w\-])", text):
            if not any(taken[m.start():m.end()]):
                s, e = extend(text, m.start(), m.end(), taken)
                hits.append((s, e, name))
                for i in range(s, e):
                    taken[i] = True
    return sorted(hits)


# a norm citation: § / Art. / article + number, then within the clause an act
# abbreviation (two capitals) or "du code …" / "de la loi …"
CITATION_RE = re.compile(
    r"(?:§§?|Art\.|Art|art\.|Artikel|[Aa]rticles?)\s?\d[^\n()\[\];:]{0,50}?"
    r"(?:(?<![\w\-])[A-ZÄÖÜ][A-Za-zÄÖÜäöü\-]*[A-ZÄÖÜ](?:\s(?:[IVX]+|\d{4}))?(?![\w\-])"
    r"|\b(?:du|de la)\s(?:[Cc]ode|loi)\b[^\n,;()]*)")


def find_untagged_citations(text, covered):
    """[(start, end)] for norm citations with no tagged character."""
    return [(m.start(), m.end()) for m in CITATION_RE.finditer(text)
            if not any(covered[m.start():m.end()])]
