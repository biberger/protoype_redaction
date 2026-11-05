"""Deterministic relabelling of canonical records to the 2026-11 conventions (GENERATION.md decisions 31-36).

Applied when records are read (`legalner.build.read_records`), so every source - synthetic, RIS, LER, EUR-Lex,
MAPA, gold sets - follows the same rules without editing raw files:

- `country`: a location or organization span that is a country name ("Österreich", "Republik Österreich",
  "Deutschlands", "la France") becomes `country` (countries stay visible in pseudonymised output).
- `date_of_birth`: a date preceded by a birth cue ("geb.", "geboren am", "Geburtsdatum:", "*", "né le").
- postal code + place: an untagged postcode directly before a location ("1010 Wien", "A-4020 Linz") is merged into
  one `address` span.
- disciplinary bodies of the professional chambers that decide cases (OBDK, "Disziplinarrat der
  Rechtsanwaltskammer Wien") are `court`, not `organization`.
- a phone number span absorbs its extension ("0222/52152 DW 3780", "Kl. 12", "Durchwahl 45").
"""
import re
import unicodedata

_COUNTRIES_DE = """
Österreich Deutschland Schweiz Liechtenstein Luxemburg Belgien Niederlande Holland Frankreich Italien Spanien Portugal
Polen Tschechien Slowakei Ungarn Slowenien Kroatien Serbien Bosnien und Herzegowina Bosnien-Herzegowina Montenegro
Kosovo Nordmazedonien Mazedonien Albanien Griechenland Bulgarien Rumänien Moldau Republik Moldau Ukraine Russland
Belarus Weißrussland Litauen Lettland Estland Finnland Schweden Norwegen Dänemark Island Irland Großbritannien
Vereinigtes Königreich England Schottland Malta Zypern Türkei Georgien Armenien Aserbaidschan Syrien Irak Iran
Afghanistan Pakistan Indien China Japan Russische Föderation Tschetschenien Somalia Eritrea Äthiopien Nigeria Ghana
Gambia Senegal Marokko Algerien Tunesien Libyen Ägypten Sudan Südsudan Kongo Kamerun Guinea Mali Sierra Leone Jemen
Libanon Jordanien Israel Palästina Saudi-Arabien Kuwait Bangladesch Sri Lanka Nepal Vietnam Thailand Philippinen
Indonesien Mongolei Kasachstan Usbekistan Tadschikistan Kirgisistan Turkmenistan USA Kanada Mexiko Brasilien
Argentinien Chile Kolumbien Venezuela Kuba Australien Neuseeland Südafrika Vereinigte Staaten
"""
_COUNTRIES_FR = """
Autriche Allemagne Suisse Liechtenstein Luxembourg Belgique Pays-Bas France Italie Espagne Portugal Pologne
République tchèque Tchéquie Slovaquie Hongrie Slovénie Croatie Serbie Bosnie-Herzégovine Monténégro Kosovo
Macédoine du Nord Albanie Grèce Bulgarie Roumanie Moldavie Ukraine Russie Biélorussie Lituanie Lettonie Estonie
Finlande Suède Norvège Danemark Islande Irlande Royaume-Uni Grande-Bretagne Angleterre Malte Chypre Turquie Géorgie
Arménie Azerbaïdjan Syrie Irak Iran Afghanistan Pakistan Inde Chine Japon Somalie Érythrée Éthiopie Nigeria Ghana
Sénégal Maroc Algérie Tunisie Libye Égypte Soudan Congo Cameroun Guinée Mali Liban Jordanie Israël États-Unis Canada
Mexique Brésil Argentine Chili Colombie Venezuela Cuba Australie Afrique du Sud Vietnam Biélorussie
"""
_LONG_FORMS = [
    "Republik Österreich", "Bundesrepublik Deutschland", "Schweizerische Eidgenossenschaft", "Fürstentum Liechtenstein",
    "Großherzogtum Luxemburg", "Königreich Belgien", "Königreich der Niederlande", "Französische Republik",
    "Italienische Republik", "Königreich Spanien", "Portugiesische Republik", "Republik Polen", "Tschechische Republik",
    "Slowakische Republik", "Republik Ungarn", "Republik Slowenien", "Republik Kroatien", "Republik Serbien",
    "Hellenische Republik", "Republik Bulgarien", "Königreich Dänemark", "Königreich Schweden", "Republik Finnland",
    "Republik Irland", "Arabische Republik Syrien", "Islamische Republik Iran", "Islamische Republik Afghanistan",
    "Russische Föderation", "Vereinigte Staaten von Amerika", "Volksrepublik China", "Republik Türkei",
    "République française", "République d'Autriche", "République fédérale d'Allemagne", "Confédération suisse",
    "Royaume de Belgique", "Grand-Duché de Luxembourg", "Royaume des Pays-Bas", "Principauté de Liechtenstein",
    "Royaume d'Espagne", "République italienne", "République de Pologne", "République portugaise",
    "République hellénique", "Royaume-Uni de Grande-Bretagne et d'Irlande du Nord", "Fédération de Russie",
    "République arabe syrienne", "Etats-Unis", "Etats-Unis d'Amérique", "États-Unis d'Amérique",
]


# names that are also cities: a country only in their long form ("Großherzogtum Luxemburg")
AMBIGUOUS = frozenset({"luxemburg", "luxembourg", "luxemburgs"})


def _norm(s):
    s = unicodedata.normalize("NFC", s).replace("’", "'").replace("‑", "-")
    return re.sub(r"\s+", " ", s).strip().casefold()


def _country_names():
    multi = (r"Bosnien und Herzegowina|Republik Moldau|Vereinigtes Königreich|Russische Föderation|Sierra Leone|"
             r"Sri Lanka|Vereinigte Staaten|République tchèque|Macédoine du Nord|Afrique du Sud")
    german = set(re.findall(rf"(?:{multi}|\S+)", _COUNTRIES_DE)) | {n for n in _LONG_FORMS if not re.search(r"[éè']|^(?:Royaume|Grand|Principaut|Confédération|Fédération|Etats|États)", n)}
    french = set(re.findall(rf"(?:{multi}|\S+)", _COUNTRIES_FR)) | set(_LONG_FORMS)
    out = {_norm(n) for n in german | french}
    for n in german:  # German genitive: Österreichs, Deutschlands, Polens, der Republik Österreichs
        if re.search(r"[a-zäöü]$", n) and not re.search(r"[sßzx]$", n):
            out.add(_norm(n + "s"))
    return frozenset(out) - AMBIGUOUS


COUNTRIES = _country_names()
BIRTH_CUE = re.compile(r"(?:\bgeb\.?|\bgeboren(?:\s+am)?|\bGeburtsdatum|\bGeb\.?-?Datum|\bGeburtstag|\bGeburtsdaten|"
                       r"\bn[ée]e?\s+le|\bdate\s+de\s+naissance|\bdate\s+of\s+birth|\bDOB|(?<![\w*])\*)"
                       r"\s*[:,]?\s*(?:am\s+)?$", re.I)
# a postcode that starts a line or follows a comma, "·", "|" or "in", on the same line as the place
POSTCODE = re.compile(r"(?:^|(?<=\n)|(?<=[,·|;]\s)|(?<=\bin\s))(?:(?:A|D|CH|F|B|L|FL|I)\s?-\s?)?\d{4,5}[ \u00a0]\Z")
DISCIPLINARY = re.compile(r"Disziplinar(?:rat|rates|kommission|senat|senates|gericht|ausschuss)|^OBDK$|"
                          r"Berufungs-\s+und\s+Disziplinarkommission|Disziplinarsenat|conseil\s+de\s+discipline", re.I)
EXTENSION = re.compile(r"\s*(?:DW|Dw\.?|Kl\.?|Klappe|Durchwahl|Nebenstelle|Nst\.|poste|ext\.?)\s*:?\s*\d{1,5}\b")


def relabel(rec):
    """Return `rec` with spans relabelled to decisions 31-36 (a new dict; the input is not changed)."""
    text = rec["text"]
    spans = [dict(s) for s in rec["spans"]]
    covered = [False] * (len(text) + 1)
    for s in spans:
        for i in range(s["start"], s["end"]):
            covered[i] = True
    for s in spans:
        lab = s["label"]
        if lab in ("location", "organization") and _norm(s["text"]) in COUNTRIES:
            s["label"] = "country"
        elif lab == "date" and (s["text"][:1] == "*" or BIRTH_CUE.search(text[max(0, s["start"] - 40):s["start"]])):
            s["label"] = "date_of_birth"
        elif lab == "organization" and DISCIPLINARY.search(s["text"]):
            s["label"] = "court"
        elif lab == "phone_number":
            m = EXTENSION.match(text, s["end"])
            if m and not any(covered[s["end"]:m.end()]):
                s["end"] = m.end()
                s["text"] = text[s["start"]:s["end"]]
        if s["label"] == "date_of_birth" and s["text"][:1] == "*":  # "*" is a birth cue like "geb." (decision 33)
            k = len(s["text"]) - len(s["text"][1:].lstrip())
            s.update(start=s["start"] + k, text=s["text"][k:])
        if s["label"] == "location" and rec.get("lang") in ("de", "fr"):  # English years: "May 28, 2012 Camden"
            line_start = text.rfind("\n", 0, s["start"]) + 1
            m = POSTCODE.search(text[max(line_start, s["start"] - 16):s["start"]])
            if m:
                start = s["start"] - (len(m.group()))
                if not any(covered[start:s["start"]]):
                    s.update(label="address", start=start, text=text[start:s["end"]])
    seen, out = set(), []
    for s in spans:
        key = (s["label"], s["start"], s["end"])
        if key not in seen:
            seen.add(key)
            out.append(s)
    return dict(rec, spans=out)
