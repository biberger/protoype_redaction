"""Austrian court decisions from the RIS OGD API, pseudonymisation filled from gazetteers.

RIS publishes decisions with party data replaced by placeholders whose style differs per
court (Justiz "A*", "* K*", "*"; BVwG "XXXX"; LVwG "***", "xxx", letter codes "AA";
VwGH initials "des M K in W"; see the annotation section). Each placeholder is classified
from its context (person, organization, address, location, date, land register, file
number, …), replaced by a gazetteer value (consistently within the document) and
labelled. Dates, case numbers, court names, addresses written in clear, judges in the
Kopf and signature, and representatives after "vertreten durch" are labelled by rule.
A placeholder no rule can classify is filled with a neutral surname and its chunk gets
meta["uncovered"] = the PII labels, so build.py does not query those labels on it.

Coverage (schema.SOURCES["ris"]) is limited to labels these rules annotate completely
enough (measured in docs/audits/ris_rules.md); anything else in RIS text (companies and
places written in clear) is left for teacher pseudo-labels.

    python -m legalner.sources.ris search --app Justiz --court OGH --since 2023-01-01 --pages 5 -o data/ris/index.jsonl
    python -m legalner.sources.ris fetch data/ris/index.jsonl --cache data/ris/raw
    python -m legalner.sources.ris convert data/ris/index.jsonl --cache data/ris/raw -o data/canonical/ris.jsonl

Hosts: data.bka.gv.at (search API) and ogd.ris.bka.gv.at (document content).
"""
import argparse
import html.parser
import json
import pathlib
import random
import re
import time
import urllib.parse
import urllib.request

from legalner.tagged import chunk, merge_date_ranges

API = "https://data.bka.gv.at/ris/api/v2.6/Judikatur"
UA = "legalner/0.1 (research; RIS OGD)"
MAX_CHARS = 1500

# --------------------------------------------------------------------------- API


def _get(url, timeout=60, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - retry transient errors
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def _as_list(x):
    return x if isinstance(x, list) else [x] if x else []


def parse_search(payload):
    """Document references from one API result page."""
    res = payload["OgdSearchResult"]["OgdDocumentResults"]
    out = []
    for ref in _as_list(res.get("OgdDocumentReference")):
        meta = ref["Data"]["Metadaten"]
        jud = meta.get("Judikatur", {})
        urls = {}
        for c in _as_list(ref["Data"].get("Dokumentliste", {}).get("ContentReference")):
            if c.get("ContentType") != "MainDocument":
                continue
            for u in _as_list(c["Urls"]["ContentUrl"]):
                urls[u["DataType"].lower()] = u["Url"]
        app = meta["Technisch"]["Applikation"]
        gz = _as_list(jud.get("Geschaeftszahl", {}).get("item"))
        out.append({
            "id": meta["Technisch"]["ID"], "app": app, "court": meta["Technisch"].get("Organ"),
            "case_numbers": gz, "date": jud.get("Entscheidungsdatum"),
            "doc_type": jud.get("Dokumenttyp"), "urls": urls,
        })
    return out, int(res["Hits"]["#text"])


PAGE_SIZES = {"Ten": 10, "Twenty": 20, "Fifty": 50, "OneHundred": 100}


def search(app="Justiz", court=None, since=None, until=None, pages=1, per_page="OneHundred", text_only=True,
           limit=None, bundesland=None, skip=()):
    """Iterate decision references (full texts only, not Rechtssätze); ids in `skip` are left out.

    `bundesland` filters LVwG decisions by state (Wien, Niederoesterreich, Oberoesterreich, Burgenland,
    Steiermark, Kaernten, Salzburg, Tirol, Vorarlberg).
    """
    params = {"Applikation": app, "DokumenteProSeite": per_page}
    if court:
        params["Gericht"] = court
    if bundesland:
        params["Bundesland"] = bundesland
    if since:
        params["EntscheidungsdatumVon"] = since
    if until:
        params["EntscheidungsdatumBis"] = until
    if text_only:
        params["Dokumenttyp.SucheInEntscheidungstexten"] = "true"
    n = 0
    for page in range(1, pages + 1):
        params["Seitennummer"] = page
        payload = json.loads(_get(API + "?" + urllib.parse.urlencode(params)))
        if "Error" in payload["OgdSearchResult"]:
            raise RuntimeError(payload["OgdSearchResult"]["Error"].get("Message"))
        refs, hits = parse_search(payload)
        for r in refs:
            if (text_only and r["doc_type"] not in (None, "Text")) or r["id"] in skip:
                continue
            yield r
            n += 1
            if limit and n >= limit:
                return
        if page * PAGE_SIZES[per_page] >= hits:
            break


def fetch(ref, cache):
    """Download the HTML (else XML) of one decision into the cache; return the path."""
    cache = pathlib.Path(cache)
    for kind in ("html", "xml"):
        if kind in ref["urls"]:
            path = cache / f"{ref['id']}.{kind}"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(_get(ref["urls"][kind]))
            return path
    return None

# ------------------------------------------------------------------- text


# contentBlocks whose heading marks document metadata, not decision text
META_HEADINGS = {"gericht", "entscheidungsdatum", "geschäftszahl", "european case law identifier", "dokumentnummer",
                 "norm", "index", "schlagworte", "sammlungsnummer", "rechtssatznummer", "im ris seit",
                 "zuletzt aktualisiert am", "entscheidungsart", "rechtsgebiet", "fundstelle", "beachte", "anmerkung",
                 "veröffentlicht", "zuletzt aktualisiert", "dokumenttyp", "rechtssatz"}
DROP_HEADINGS = {"text", "betreff"}  # headings that carry no content of their own


class _Blocks(html.parser.HTMLParser):
    """Block-level text extraction that works for RIS HTML and risdok XML alike.

    RIS HTML repeats every paragraph that contains a norm citation in a
    screen-reader form (`<span class="sr-only">… Paragraph 16 a, Absatz eins …`);
    those spans are skipped. Metadata blocks (Gericht, Geschäftszahl, ECLI, …)
    are dropped together with their `<h1>` heading.
    """
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table", "absatz",
             "ueberschrift", "abschnitt", "titel", "td"}
    SKIP = {"script", "style", "head", "metadaten", "title"}
    VOID = {"br", "meta", "img", "hr", "input", "link", "col", "area", "base", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack, self.drop = [], [], False
        self.heading = None  # index into parts where the current <h1> started

    @property
    def skip(self):
        return any(self.stack)

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        if tag not in self.VOID:
            self.stack.append(tag in self.SKIP or "sr-only" in cls.split())
        if tag == "h1":
            self.heading = len(self.parts)
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()
        if tag == "h1" and self.heading is not None:
            title = re.sub(r"\s+", " ", "".join(self.parts[self.heading:])).strip().rstrip(":").lower()
            self.drop = title in META_HEADINGS
            if self.drop or title in DROP_HEADINGS:
                del self.parts[self.heading:]
            self.heading = None
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and (not self.drop or self.heading is not None):
            self.parts.append(data)


def markup_to_text(markup):
    p = _Blocks()
    p.feed(markup)
    text = "".join(p.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

# ---------------------------------------------------------------- annotation
#
# Placeholder styles seen in RIS (2022+):
#   Justiz   "A*", "Bö*", "* K*" (first name + surname), "Mag. A* B*", "*" (address, place,
#            day+month in "geboren am * 2012"), older decisions "A*****"
#   BVwG     "XXXX" for every redacted item (names, dates, places, file numbers)
#   LVwG     "***", "****", "xxx" (Kärnten), "XX.XX.XXXX"; Tirol uses letter codes "AA", "BB",
#            "Adresse 1, **** Z"; NÖ uses single letters "des A", "B Rechtsanwalts GmbH"
#   VwGH     initials: "der D J", "des M K in W", "mitbeteiligte Partei: R W in W"
#   VfGH     parties are rarely named at all ("die beschwerdeführende Partei")

DEGREE_TOK = (r"Univ\.-Prof\.|Hon\.-Prof\.|Ao\.\s?Univ\.-Prof\.|Priv\.-Doz\.|PD|Prof\.|Ing\.\s?Mag\.|Ing\.\s?Dr\.|Mag\.\s?\(FH\)|DI\s?\(FH\)|DDrin\.|DDr\.|Dr\.in|Dr\.|Mag\.a|"
              r"MMag\.|Maga\.|Mag\.|Dipl\.-Ing\.|DI|Ing\.|Bakk\.|"
              r"MMag(?=\s)|Mag(?=\s)|Dr(?=\s)")  # LG/OLG Kopf without dots: "Mag Rak", "Dr Huber"
# a degree is followed by a space, or directly by the name after a dot ("Dr.Bott", "Maga.Fabsits")
DEGREE = rf"(?:(?:{DEGREE_TOK})(?:\s|(?<=\.)(?=[A-ZÄÖÜ][a-zäöü])))"
POSTNOM = r"(?:(?:,?\s(?:LL\.M\.|LLM|MBA|MAS|MSc|BSc|BA|MA|PhD|Bakk\.\s?phil\.|Bakk\.)(?![\w])){1,3})"
_LOW = r"a-zäöüßéèáàíóúčćšžđıçğşñ'’"
_WORD = rf"(?!(?:{DEGREE_TOK}|Brigadier|Oberst|Major|Senatspräsident|Vizepräsident|Präsident|Hofr|Richter|Vorsitzend)\w*)(?:[A-ZÄÖÜ][{_LOW}]+|[A-ZÄÖÜ]{{2,}}(?![a-z.]))"
NAME = rf"{_WORD}(?:-{_WORD})?"
PERSON_NAME = rf"{DEGREE}*(?:(?:{NAME}|[A-ZÄÖÜ]\.)\s){{0,3}}{NAME}{POSTNOM}?"

# one placeholder token: Justiz "A*"/"Bö*"/"*"/"A*****", BVwG "XXXX", LVwG "***"/"xxx"/"**1",
# VwGH bracketed initials "Herrn Mag. [B]", "der [A B]" (not "[D]er" in quotes, not "[sic!]")
BRACKET_PH = r"\[[A-ZÄÖÜ]\.?(?:\s?[A-ZÄÖÜ]\.?){0,2}\](?![\wäöüß])"
PH = r"(?:" + BRACKET_PH + r"|(?<![\w*])[A-ZÄÖÜ][a-zäöü]{0,2}\*+(?!innen)|\*+\d+|\*{3,}[a-z](?![a-zäöü])|(?<![a-zäöü])\*+(?![a-zäöü])|XXXX|(?<![a-wyzäöüß])x{2,}(?=[a-zäöüß]{3,}|\b))"
PH_RUN = re.compile(rf"(?:{DEGREE})*{PH}(?:[ \-]{PH})*(?:[a-zäöüß]+)?")
DATE_PH = re.compile(r"(?<![\w*])(?=[^\s]*[Xx*])(?:[Xx]{2}|\*{1,2}|\d{1,2})\.\s?(?:[Xx]{2}|\*{1,2}|\d{1,2})\.\s?"
                     r"(?:[Xx]{4}|\*{4}|(?:19|20)\d\d)(?![\w*])")
_STREET_SUFFIX = r"(?:[Ss]tra(?:ß|ss)e|[Gg]asse|[Ww]eg|[Pp]latz|[Aa]llee|[Rr]ing|[Kk]ai|[Ll]ände|[Zz]eile|[Pp]romenade|[Ss]teig)"
_PH_WORD = r"(?:[A-ZÄÖÜ][a-zäöü]{0,2}\*+|\*+|XXXX|xxx)"
STREET_PH = re.compile(  # a street whose name and/or house number is redacted, with postcode and town if redacted too
    rf"(?:(?:\*{{2,4}}|\d{{4}})\s(?:[A-ZÄÖÜ][a-zäöü]{{0,2}}\*+|[A-ZÄÖÜ][\w\-]+),\s)?"  # "** B*, **straße **"
    rf"(?:(?<![\w*])(?:[A-ZÄÖÜ][a-zäöü]{{0,2}})?\*+-?{_STREET_SUFFIX}|\b[A-ZÄÖÜ][\w\-]*{_STREET_SUFFIX}|"
    rf"\b[A-ZÄÖÜ][\w\-]*\s(?:Straße|Gasse|Weg|Platz|Allee|Ring))\s(?:{_PH_WORD}|\d+[a-z]?)(?:/(?:\*+|\d+))*"
    rf"(?:,\s(?:(?:\*+|\d{{4}})\s)?(?:{_PH_WORD}|[A-ZÄÖÜ][\w\-]+)(?=[,;)“]|\s(?:vertreten|wegen|in)\b))?"
    r"(?:\sin\s[A-ZÄÖÜ][a-zäöü]{0,2}\*+)?")
# "Adresse 2, ***** Y" (LVwG Tirol: numbered address, redacted postcode, letter-coded town), "**** Z" (postcode, town)
ADDR_CODE = re.compile(r"(?<![\w*])\*{2,4}\s[A-ZÄÖÜ][a-zäöü]{0,2}\*+|\bAdresse\s\d+(?:,?\s(?:in\s)?(?:\*{4,5}|\d{4})\s"
                       r"[A-ZÄÖÜ](?![\w.])(?:\sStadt\b)?)?|(?<![\w*])\*{4,5}\s[A-ZÄÖÜ](?![\w.])(?:\sStadt\b)?")
TOWN_CODE = re.compile(r"\*{4,5}\s[A-ZÄÖÜ](?:\sStadt)?")
# VwG Wien abbreviates street names to the initial: "an der Adresse C.-platz in Wien", "Wien, G.-Park, Tür ..."
CODE_STREET = re.compile(
    r"(?:\b(?:Wien|\d{4}\s[A-ZÄÖÜ][a-zäöü]+),\s)?\b[A-ZÄÖÜ]\.-(?:[Pp]latz|[Gg]asse|[Ss]tra(?:ß|ss)e|[Ww]eg|[Pp]ark|[Rr]ing|"
    r"[Aa]llee|[Zz]eile|[Kk]ai|[Ll]ände|[Pp]romenade|[Hh]of|[Ss]iedlung)(?:\s\d+[a-z]?(?:/\d+)*)?"
    r"(?:,?\s(?:Stiege|Tür|Top)\s(?:\d+|\.\.\.|…|[A-ZÄÖÜ]\.?))*(?:\s(?:in|,)\s?(?:Wien|\d{4}\s[A-ZÄÖÜ][a-zäöü]+))?")
LETTER_CODE = re.compile(r"\b([A-ZÄÖÜ])\1\b(?!\.)")  # LVwG Tirol "AA", "BB"
_PERSON_CUE = (r"(?:des|der|dem|den|die|von|Herrn?|Frau|Partei:?|Revisionswerbers?|Revisionswerberin|"
               r"Mitbeteiligten|Beschwerdeführers?|Beschwerdeführerin|Nachbarn|Zeugen|Zeugin|Ehegattin|Ehemann|"
               r"Mutter|Vater|Sohn|Tochter|\d\.|mj\.|durch|für|Inhaber(?:in)?)")
INITIALS = re.compile(
    rf"\b{_PERSON_CUE}\s((?:{DEGREE})*(?:mj\.\s)?[A-ZÄÖÜ]\.?(?:\s[A-ZÄÖÜ]\.?){{0,2}})(?=,|\)|;|\sin\s[A-ZÄÖÜ]\b|"
    r"\s(?:vertreten|gegen|als|und\s(?:\d\.\s)?(?:de[rs]\s)?(?:mj\.\s)?[A-ZÄÖÜ]\b|geb|wohnhaft))")
PAIR_CODES = re.compile(r"(?<![\w.§/])([A-ZÄÖÜ])\s(?:und|sowie|bzw\.)\s([A-ZÄÖÜ])(?![\w.\-/)])")  # LVwG NÖ "B und C"
CODE_ADDRESS = re.compile(r"\b[A-ZÄÖÜ]-(?:Straße|Gasse|Weg|Platz)\s?(?:\d+\s?)?,\s[A-ZÄÖÜ]-Ort\b|"  # LVwG Stmk
                          r"(?<=,\s)[A-ZÄÖÜ],\s[A-ZÄÖÜ][\s-](?:Straße|Gasse|Weg|Platz)(?:\s\d+[a-z]?)?(?=[,;)])")
# LVwG Burgenland/Steiermark name the redacted item in brackets: "[Vertreter 1]", "[KG]", "[EZ2]", "[Klinik]"
DESCRIPTOR_PH = re.compile(r"\[(Vertreter(?:in)?|Beschwerdeführer(?:in)?|Name|KG|EZ|Adresse|Gemeinde|Ort|Klinik|Apotheke|"
                           r"Detektei|Firma|Unternehmen|Gasthaus|Hotel)\s?\d*\]")
DESCRIPTOR_LABEL = {"Vertreter": "person", "Vertreterin": "person", "Beschwerdeführer": "person",
                    "Beschwerdeführerin": "person", "Name": "person", "KG": "location", "Gemeinde": "location",
                    "Ort": "location", "EZ": "land_register_id", "Adresse": "address"}
CODE_PLACE = re.compile(r"\b[A-ZÄÖÜ]-(?:Ort|Stadt|Dorf|Gemeinde)\b")
TOWN_INITIAL = re.compile(r"(?<=\s)(?:in|aus|nach|Bezirkshauptmannschaft|BH|KG|Gemeinde|Stadtgemeinde|Marktgemeinde|Stadt|"
                          r"Magistrat|Bezirk|Landespolizeidirektion|in\sdie|in\sden|in\sder)"
                          r"\s([A-ZÄÖÜ])(?=[,;)]|\s(?:vom|gegen|vertreten|und|zu|\()|\.\s[A-ZÄÖÜ])")

MONTHS = "Jänner|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
MONTH_NAMES = MONTHS.split("|")[1:]
DATE_RE = re.compile(rf"\b(?:[0-3]?\d\.\s?(?:[01]?\d\.\s?(?:18|19|20)\d\d|(?:{MONTHS})\s(?:18|19|20)\d\d))\b|"
                     r"(?:(?<=\bv\s)|(?<=\bvom\s)|(?<=\bam\s))[0-3]?\d\.\s?[01]?\d\.\s?\d\d\b(?![.\d])")
CASE_RE = re.compile(
    r"\b(?:\d{1,3}\s?[A-Z][A-Za-z]{0,3}\s?\d{1,5}/\d{2}[a-z](?:-\d+(?:\.\d+)?)?|"                                   # Justiz: 7 Ob 161/26s, 26 Cg 77/24m-24
    r"R[aorsv]\s?\d{4}/\d{2}/\d{4}(?:\sbis\s\d{4})?|"                  # VwGH: Ra 2019/02/0138
    r"(?:E|G|V|W|U|B|WI|SV|KR|KI|UA)\s?\d{1,5}/\d{4}(?:-\d+)?(?:\su\.a\.)?|"  # VfGH: E 1234/2024, G 100/2024
    r"[WGIL]\s?\d{3}\s\d{7}-\d(?:/\d+[EZ])?|"                          # BVwG: W175 2256340-1/10E
    r"LVwG-[A-Z0-9][A-Za-z0-9\-/.]*\d|VGW-[\d/\-]+\d|"                  # LVwG NÖ/Stmk/OÖ, VGW Wien
    r"LVwG\s\d+\.\d+-\d+/\d{4}(?:-\d+)?|"                              # LVwG Salzburg/Stmk: LVwG 30.1-123/2024
    r"KLVwG-[\d/\-]+\d|LVwG-?\d{4}/\d+/\d+(?:-\d+)?|"                   # Kärnten, Tirol: LVwG-2026/17/2033-5
    r"\d{3}\.\d{3}/\d{4}/\d{2}|"                                       # LVwG Vorarlberg/Bgld style
    r"RV/\d{4}-\d{2}/\d{4})")                                             # BFG
AUTHORITY_GZ = re.compile(  # "Zl. 1280893010-210968115", "GZ: 207263/2022", "OB: 29240197700011"
    r"(?:\bZl\.?:?|\bZahl:?|\bGZ\.?:?|\bGZl\.?|\bAZ:?|Geschäftszahl:?|Aktenzahl:?|\bOB:?|Verfahrenszahl:?)\s"
    r"((?:[A-ZÄÖÜ]{1,4}\s)?(?=[\w./\-]*\d)[A-Za-z0-9ÄÖÜ][\w./\-]*?(?:[\-/.][\w]+)*)(?=[,;)]|\s|$)")
_CITY = r"(?:Wien|Graz|Linz|Innsbruck|Salzburg|Klagenfurt(?:\sam\sWörthersee)?|St\.\sPölten|Eisenstadt|Bregenz)"
COURT_RE = re.compile(
    r"\b(?:Oberste[nr]?\s(?:Gerichtshof(?:es|s)?|Patent-\sund\sMarkensenat(?:es|s)?)|OGH|"
    r"Verfassungsgerichtshof(?:es|s)?|VfGH|Verwaltungsgerichtshof(?:es|s)?|VwGH|"
    r"Bundesverwaltungsgericht(?:es|s)?|BVwG|Bundesfinanzgericht(?:es|s)?|BFG|"
    r"Verwaltungsgericht(?:es|s)?\sWien|VwG\sWien|"
    r"Oberlandesgericht(?:es|s)?\s(?:Wien|Graz|Linz|Innsbruck)|OLG\s(?:Wien|Graz|Linz|Innsbruck)|"
    r"Landesgericht(?:es|s)?\sfür\s(?:Zivilrechtssachen|Strafsachen)\s(?:Wien|Graz)|LGZ\s?Wien|LGZ\s?Graz|"
    r"(?:LG|Landesgericht(?:es|s)?)\sfür\s(?:ZRS|Zivilrechtssachen|Strafsachen)\s(?:Wien|Graz)|LGSt\s?Wien|"
    r"Arbeits-\sund\sSozialgericht(?:es|s)?\sWien|ASG\sWien|Handelsgericht(?:es|s)?\sWien|HG\sWien|"
    r"Jugendgericht(?:es|s)?hof(?:es|s)?\sWien|"
    r"(?:Landesgericht(?:es|s)?|LG)\s(?:als\s\w+\s)?(?:St\.\s)?(?!HR\b|Dr\b|Mag\b)(?:" + NAME + r")(?:\s(?:an\sder|am|im|ob\sder)\s"
    r"(?![A-ZÄÖÜ]\w*verfahren)" + NAME + r")?|"
    r"(?:Bezirksgericht(?:es|s)?|BG)\s(?:für\sHandelssachen\sWien|(?:Innere\sStadt\s)?(?:" + NAME + r")"
    r"(?:\s(?:an\sder|am|im|ob\sder)\s(?![A-ZÄÖÜ]\w*verfahren)" + NAME + r")?)|"
    r"Landesverwaltungsgericht(?:es|s)?\s(?:Niederösterreich|Oberösterreich|Steiermark|Kärnten|Tirol|Salzburg|"
    r"Vorarlberg|Burgenland|Wien)|"
    r"LVwG\s(?:Niederösterreich|Oberösterreich|Steiermark|Kärnten|Tirol|Salzburg|Vorarlberg|Burgenland|"
    r"NÖ|OÖ|Stmk)|"
    r"(?:Europäische[nr]?\sGerichtshof(?:es|s)?\sfür\sMenschenrechte|EGMR|Gerichtshof(?:es|s)?\sder\s"
    r"Europäischen\sUnion|EuGH)|Verwaltungsgericht(?:es|s)?\s(?:des\sBundes\sfür\sFinanzen)|"
    r"(?:Bundes|Landes)verwaltungsgerichte[n]?)(?![\wäöü])")
_NOT_CITY_AFTER_LG = {"Gerichtshof", "Strafsachen", "Wien"}

JUDGE_WORDS = (r"V?Präs\.d\.(?:LG|OLG|BG)(?:\sHR)?|Senatspräsident(?:in|en)?|Vizepräsident(?:in|en)?|Präsident(?:in|en)?|Hofrät(?:in|innen|e|en)?|"
               r"Hofrat(?:es)?|Richter(?:in|innen|s|n)?|Rechtspfleger(?:in)?|Einzelrichter(?:in)?|"
               r"Senatsvorsitzende[nr]?|Vorsitzende[nr]?|(?:fachkundige[nr]?\s)?Laienrichter(?:n|in|innen)?|"
               r"Anwaltsrichter(?:in|s)?|Mitglied(?:er)?\sdes\sSenates|(?<=sein\s)Mitglied|(?<=ihr\s)Mitglied|Beisitzer(?:in|innen)?|"
               r"Schriftführer(?:in|s)?|Berichter(?:in)?|Referent(?:in)?")
JUDGE_INTRO = re.compile(
    rf"(?:\b(?:{JUDGE_WORDS})(?:\sdes\s(?:Obersten\sGerichtshofs?|Verwaltungsgerichtshofes|Oberlandesgerichts|"
    r"Landesgerichts|Bezirksgerichts|Bundesverwaltungsgerichts|Landesverwaltungsgerichts)(?:\s(?:Wien|Graz|Linz|"
    r"Innsbruck|für\sZivilrechtssachen\s(?:Wien|Graz)|für\sStrafsachen\s(?:Wien|Graz)|[A-ZÄÖÜ][a-zäöü]+))?|"
    r"\saus\sdem\sKreis\sder\s\w+(?:\s\w+)?)?(?:\s(?:FOI|ADir|RegR|OAR|ADir\.|Amtsrat|Amtsrätin|VB))?\s|"
    rf"\bals\sVorsitzende[nr]?\s(?:sowie|und)\s(?:(?:die|den)\s)?(?=(?:{DEGREE_TOK})\s)|"
    rf"(?<!vertreten\s)\bdurch\s(?:(?:den|die|seinen|seine|ihre[n]?)\s)?(?:(?:Richter(?:in)?|Einzelrichter(?:in)?|"
    rf"Vorsitzende[nr]?)\s)?(?=(?:{DEGREE_TOK})\s))")
_NAME_RE = re.compile(PERSON_NAME)
DEGREE_NAME = re.compile(rf"(?<![\w.])(?:{DEGREE})+(?:(?:{NAME}|[A-ZÄÖÜ]\.)\s){{0,3}}{NAME}{POSTNOM}?")
_LIST_SEP = re.compile(r"(?:\s\([^)]{1,20}\))?(?:\sals\sVorsitzende[nr]?)?(?:,\s(?:sowie\s|und\s)?|\sund\s|\ssowie\s)"
                       r"(?:die\s|den\s|der\s)?(?:(?:Hofr\w+|Richter\w*)\s)?(?=[A-ZÄÖÜ])")
LAWYER_INTRO = re.compile(r"(?:vertreten\sdurch|Verteidiger(?:in)?:?|Verfahrenshelfer(?:in)?:?)\s(?:die\s|den\s)?(RA\s)?")
LAWYER_AFTER = re.compile(r"(?:\sua)?,?\s(?:Rechtsanw|Notar|Verteidiger|Anwält|RA\b)")
SIGNATURE = re.compile(rf"\n({PERSON_NAME})\n+\((?:Richter|Richterin|Einzelrichter|Einzelrichterin|Vorsitzende|"
                       r"Vorsitzender)\)")

LEGAL_FORMS = (r"GmbH(?:\s&\sCo\.?\s?KG)?|AG|KG|OG|SE|KEG|OEG|eGen|reg\.Gen\.m\.b\.H\.|GesmbH|Ges\.m\.b\.H\.|"
               r"Gesellschaft\sm\.b\.H\.|e\.U\.|eU|Privatstiftung|Stiftung|Verein|Bank|Sparkasse|Versicherung|"
               r"Anwaltsgesellschaft\smbH|Rechtsanwälte\sGmbH|Rechtsanwalts\sGmbH|Rechtsanwälte\sOG|"
               r"Rechtsanwälte|Ltd\.?|Inc\.?|S\.A\.|S\.r\.l\.|s\.r\.o\.|Sp\.\sz\so\.o\.|LLC|B\.V\.")
_ORG_AFTER = re.compile(rf"^(?:\s(?:[A-ZÄÖÜ][\w\-]*\s){{0,2}}(?:{LEGAL_FORMS}))(?![\w])")
_PRE = {  # regexes on the text just before a placeholder, in priority order
    "street_after": None,
    "land_register_id": re.compile(
        r"(?:\bEZ:?|\bKG|\bGst\.?(?:-?Nr\.?)?|GST-NR|\bGp\.?|Grundstück(?:e|es|s|en)?(?:\s(?:Nr\.?|Nrn\.?))?|"
        r"Gste?\.?\s?Nrn?\.?|Einlagezahl|Katastralgemeinde|\bGB|Grundbuch|Bauplatz|Liegenschaft\sEZ|"
        r"(?:Weg|Güterweg)?[Pp]arzelle(?:nnummer|\sNr\.?|\sNummer)?|Parz\.?(?:\s?Nr\.?)?)\s*$"),
    "case_number": re.compile(r"(?:\bOB:?|Verfahren|Aktenzeichen:?|\bZl\.?:?|\bZahl:?|\bGZ\.?:?|\bGZl\.?|\bAZ:?|\bZlen\.?|Aktenzahl|Geschäftszahl:?|"
                              r"Verfahrenszahl:?|IFA-Zahl(?:/Verfahrenszahl)?:?|Akt|"
                              r"\bvom\s[0-3]?\d\.\s?[01]?\d\.\s?(?:19|20)\d\d,)\s*$"),
    "company_register_number": re.compile(r"\b(?:FN|Firmenbuchnummer|ZVR(?:-Zahl)?|Handelsregister\w*):?\s*$"),
    "other_identifier": re.compile(r"(?:\bHNR:?|\bTop|(?:\b|(?<=[a-z]))[Nn]ummer:?|\bNr\.?:?|Ausweis\w*|Reisepass\w*|Konto\w*|IBAN|"
                                   r"Sozialversicherungsnummer|SVNr\.?|PIN|Account|Telefonnummer|Tel\.?)\s*$"),
    "license_plate": re.compile(r"Kennzeichen:?\s*$|Kennz\.:?\s*$"),
    "url": re.compile(r"(?:://|www\.)$|@$"),
    "judge": re.compile(rf"(?:\b(?:Richter(?:in)?|Einzelrichter(?:in)?|Vorsitzende[nr]?|Anwaltsrichter(?:s|in)?|"
                        r"Senatspräsident\w*|Hofr\w+))\s(?:(?:{DEGREE_TOK})\s)*$".replace("{DEGREE_TOK}", DEGREE_TOK)),
    "date": re.compile(r"(?:\bgeb\.|\bgeboren|\bam|\bvom|\bAm|\bVom|\bseit|\bSeit|\bbis|\bab|\bzum|\bdatiert\s(?:mit)?|"
                       r"\bmit|\bEingabe\svom|\bSchreiben\svom|\bBescheid\svom)\s*$"),
    "address": re.compile(r"(?:\bp\.\s?A\.?|per\sAdresse|wohnhaft(?:\sin)?|whft\.|Anschrift:?|Adresse:?|Wohnadresse|Wohnsitz(?:\sin)?|"
                          r"Liegenschaftsadresse|Zustelladresse|Meldeadresse|Objekt)\s*$"),
    "person": re.compile(rf"(?:\b(?:Herrn?|Frau|Beschwerde\s(?:des|der|von)|Revision\s(?:des|der)|Antrag\s(?:des|der)|"
                         r"Partei:?|Inhaber(?:in)?|Antragsteller(?:in)?|Antragsgegner(?:in)?|Beschwerdeführers?|Beschwerdeführerin|"
                         r"Kläger(?:in|s)?|Beklagte[nr]?|Angeklagte[nr]?|Beschuldigte[nr]?|Zeugen?|Zeugin|"
                         r"Sachverständige[nr]?|Gutachter(?:in|s)?|Dolmetscher(?:in|s)?|Ehegatt(?:e|in|en)|"
                         r"Gatt(?:e|in|en)|Lebensgefährt(?:e|in|en)|Mutter|Vater|Sohn|Tochter|Bruder|Schwester|"
                         r"Onkel|Tante|Neffe|Nichte|Cousin|Cousine|Großvater|Großmutter|Kind(?:es)?|"
                         r"BF\d?|Asylwerber(?:in|s)?|Mitbeteiligte[nr]?|Geschäftsführer(?:in|s)?|Obmann|"
                         r"Eigentümer(?:in|s)?|Arbeitnehmer(?:in|s)?|Lenker(?:in|s)?|Verstorbenen|Erblasser(?:in|s)?|"
                         r"Opfer[s]?|vertreten\sdurch|gegen|für|mit|und|sowie|\d\.\)?|mj\.?|Ing\.|Dr\.|Mag\.(?:a)?|DI|Hr\.|Fr\.|"
                         r"(?:Rev|Gr|Bez|Abt|Kontr|Chef)?Insp\.?|ASV|Amtssachverständige[nr]?|Familie|"
                         r"(?:Berufung|Beschwerde|Antrag|Einspruch|Anzeige|Schreiben|Stellungnahme)\svon|Unterschrift|Name[n]?|namens|genannt)|\b(?:des|der|dem|den|die))\s*$"),
    "location": re.compile(r"(?:\b(?:Tatort:?|Feuerwehr|Nachbarschaft|Agrargemeinschaft|Ort:|(?:Eigen)?[Jj]agdgebiet(?:es)?|in|nach|aus|bei|Ort|Dorf|Stadt|Provinz|Gouvernement|Bezirk|Distrikt|Region|"
                           r"Heimatort|Heimatdorf|Herkunftsort|Geburtsort|Gemeinde|Stadtgemeinde|Marktgemeinde|"
                           r"Bezirkshauptmannschaft|BH|Landespolizeidirektion|Polizeiinspektion|PI|"
                           r"Rechtsanwaltskammer|Landesstelle|Magistrat(?:\sder\sStadt)?|Stadt|Grenzübergang|"
                           r"Flughafen|Justizanstalt|Bundesland|Raum|Umgebung\svon|Nähe\svon|nahe|"
                           r"Landeshauptmann(?:es)?\svon|Bürgermeister(?:s)?\sder\s(?:Stadt|Markt)?gemeinde|"
                           r"Abteilung|Krankenhaus|Spital|Schule|Universität|Heimatstadt|Ortschaft|"
                           r"Bezirksgericht(?:s|es)?|Landesgericht(?:s|es)?|Staatsanwaltschaft|Oberstaatsanwaltschaft|"
                           r"Polizei|BPD|LPD|Disziplinarrat|Verhandlungsort|Standort|BH-|Bezirkshauptmannschaft\s))\s*$"),
}
_COUNTRIES = (r"Deutschland|Schweiz|Italien|Ungarn|Slowenien|Tschechien|Tschechische\sRepublik|Slowakei|Liechtenstein|"
              r"Kroatien|Polen|Rumänien|Bulgarien|Frankreich|Niederlande|Belgien|Luxemburg|Spanien|Serbien|"
              r"Bosnien\sund\sHerzegowina|Türkei|USA|Vereinigtes\sKönigreich|Großbritannien|Irland|Zypern|Malta")
_ADDR_FOLLOW = (rf"^(?:,\s(?:{_COUNTRIES})\b|,\s(?:vertreten|wegen|gegen|als|über|beide|alle|diese[rs]?|ebenda)\b|"
                r"\s?\)|;)")
_BARE = re.compile(r"^(?:\*+|XXXX|x{2,}|\.\.\.|…)$")
ELLIPSIS_PH = re.compile(r"(?<=[\s(])(?:\.\.\.|…)(?=[\s,;)]|$)")  # LVwG/VwG Wien


COURT_SEAT = re.compile(r"\b(?:Landesgericht(?:es|s)?(?:\sfür\s(?:Strafsachen|Zivilrechtssachen|ZRS))?|"
                        r"Oberlandesgericht(?:es|s)?|Handelsgericht(?:es|s)?|Bezirksgericht(?:es|s)?|"
                        r"Arbeits-\sund\sSozialgericht(?:es|s)?|LG|OLG|BG|HG)\s$")
COURT_SEATS = {"Oberlandesgericht": ["Wien", "Graz", "Linz", "Innsbruck"],
               "für": ["Wien", "Graz"], "Handelsgericht": ["Wien"], "Arbeits": ["Wien"],
               "Landesgericht": ["Linz", "Wels", "Steyr", "Ried im Innkreis", "Salzburg", "Innsbruck", "Feldkirch",
                                 "Klagenfurt", "Leoben", "Korneuburg", "Krems an der Donau", "St. Pölten",
                                 "Wiener Neustadt", "Eisenstadt"],
               "Bezirksgericht": ["Mödling", "Baden", "Hernals", "Leopoldstadt", "Gmunden", "Bregenz", "Villach",
                                  "Hallein", "Kufstein", "Weiz", "Amstetten", "Neusiedl am See"]}


def classify_placeholder(before, after, surface, prev=None):
    """Guess what a placeholder replaced from its context.

    `prev` is (label, gap) of the previous placeholder: a bare placeholder right after a
    party name ("Partei A*, *, vertreten") is that party's address, and a list continues
    the previous label ("Grundstücke ***, *** und ***").
    """
    bare = bool(_BARE.match(surface))
    if DATE_PH.fullmatch(surface):
        return "date"
    if bare and re.search(r"\b(?:Ende|Anfang|Mitte)\s$", before):  # a month or year
        return "date"
    if re.match(r"^\s?(?:19|20)\d\d\b", after) and bare:  # "geboren am * 2012": day and month removed
        return "date"
    if bare and _PRE["land_register_id"].search(before):  # "EZ * KG *": KG is the Katastralgemeinde
        return "land_register_id"
    if re.search(r"(?:€|\bEUR|\bEuro|\(€\):?|Freiheitsstrafen?\svon|Strafrest:?|Geldstrafe\svon)\s?$", before) \
            or re.match(r"^\s?(?:€|EUR|Euro|Jahre[n]?|Monate[n]?|Wochen|Tage[n]?|Uhr|Stunden|Minuten|Prozent|%|m²|"
                        r"km|cm|kg)\b", after):
        return "amount"  # redacted sums, durations and measures are not entities
    if bare and prev and prev[0] == "amount" and prev[1] in (" und ", ", ", " bis "):
        return "amount"  # "Freiheitsstrafe von ***** und *****"
    if bare and COURT_SEAT.search(before):
        return "court_town"  # "Landesgerichtes für Strafsachen *****": the seat; the court rule tags the whole name
    if bare and prev and prev[0] == "date" and prev[1] == ", " and re.search(
            r"gericht\w*(?:\sfür\s\w+)?\s\S+\svom\s\S+,\s$", before):
        return "case_number"  # "des Oberlandesgerichtes ***** vom *****, *****,"
    if bare and re.search(r"\bzu\s$", before) and re.match(r"^\s(?:und\s\S+\s)?des\s\w*[Gg]erichtes", after):
        return "case_number"  # "die zu ***** des Landesgerichtes … verhängte Strafe"
    if _ORG_AFTER.match(after) or re.search(r"\b(?:Firma|Unternehmens?|Verein(?:s)?|Gesellschaft|Klinik|"
                                            r"Krankenanstalt|Verwaltungsgemeinschaft)\s$", before):
        return "organization"
    if re.match(r"^-?(?:Straße|Strasse|Gasse|Weg|Platz|Allee|Ring|Kai|Lände|Zeile|Promenade)", after):
        return "street"
    if prev:
        plab, gap = prev
        if re.fullmatch(r",\s|\s(?:und|sowie|bzw\.?|oder)\s|,\s(?:und|sowie)\s", gap) and plab in (
                "land_register_id", "case_number", "license_plate") and bare:
            return plab
        if re.fullmatch(r"\s?,\s", gap) and plab in ("person", "organization", "location", "lawyer") and bare:
            return "address"
        if re.fullmatch(r",\s", gap) and plab == "address" and bare:
            return "address"  # "***, ***": street, then town
    for label in ("land_register_id", "company_register_number", "case_number", "license_plate", "url",
                  "other_identifier", "judge"):
        if _PRE[label].search(before):
            return label
    if re.search(r"(?:xx|XXXX|\*)[a-wyzäöüß][a-zäöüß]*$", surface):
        return "location"  # "xxxtales", "***bach": a field or river name
    if re.match(DEGREE, surface) or re.match(r"^(?:[A-ZÄÖÜ][a-zäöü]{0,2})?\*+[ \-][A-ZÄÖÜ][a-zäöü]{0,2}\*+", surface):
        return "person"
    if bare and _PRE["date"].search(before):
        return "date"
    if _PRE["address"].search(before) or (re.match(r"^,\s*\d{4}\s", after) and bare) or (
            bare and re.search(r",\s$", before) and re.match(_ADDR_FOLLOW, after)):
        return "address"
    if _PRE["location"].search(before) and not re.search(r"\b(?:Beschwerde|Revision|Antrag)\s(?:von)\s*$", before):
        return "location"
    if re.search(r"\bgegen\s$", before):  # an attorney as party (Disziplinarsache gegen …) is a person
        pass
    elif re.match(r"^,?\s(?:Rechtsanw(?:alt|ältin)|Verteidiger(?:in)?)\b", after) or re.search(
            r"(?:Rechtsanw(?:alt|ältin)|Verteidiger(?:in|s)?)\s$", before):
        return "lawyer"
    if _PRE["person"].search(before) or (bare and re.match(r"^,?\s(?:StA\.|geb\.|geboren)", after)):
        return "person"
    if re.match(r"^[A-ZÄÖÜ][a-zäöü]{0,2}\*", surface):  # Justiz "A*" without other cues: a name
        return "person"
    return "unknown"


def _date_value(rng, style, year=None, birth=False):
    """A filled date: birth dates 16-80 years before the decision, other dates in the 10 years before it."""
    year = year or 2024
    y = rng.randint(year - 80, year - 16) if birth else rng.randint(year - 10, year)
    d, m = rng.randint(1, 28), rng.randint(1, 12)
    if style == "daymonth":
        return f"{d}. {MONTH_NAMES[m - 1]}"
    if style == "long":
        return f"{d}. {MONTH_NAMES[m - 1]} {y}"
    return f"{d:02d}.{m:02d}.{y}"


class Filler:
    """Consistent replacement values for one document."""

    def __init__(self, gaz, rng, app=None, year=None):
        self.year, self.birth = year, False
        self.gaz, self.rng, self.app, self.memo = gaz, rng, app, {}

    def value(self, label, surface, style=None):
        key = (label, surface, style)
        if key in self.memo and _BARE.match(surface) is None:
            return self.memo[key]
        rng, gaz = self.rng, self.gaz
        degree = " ".join(re.findall(rf"(?:{DEGREE_TOK})(?=\s)", surface))
        core = re.sub(rf"^(?:(?:{DEGREE_TOK})\s)+", "", surface)
        if label in ("person", "judge", "lawyer"):
            n_parts = len(re.findall(r"[A-ZÄÖÜ][a-zäöü]{0,2}\*+|\*+|XXXX|xxx|\b[A-ZÄÖÜ]{1,2}\b", core)) or 1
            single = re.match(r"^(?:[A-ZÄÖÜ][a-zäöü]{0,2}\*|\[[A-ZÄÖÜ]\.?\]$)", core)  # "A*", "[B]": a surname
            name = gaz.surname("AT") if n_parts == 1 and single else gaz.person("AT")
            val = f"{degree} {name}".strip()
        elif label == "organization":
            val = gaz.surname("AT")
        elif label == "address":
            val = gaz.address("AT")
        elif label in ("location", "url"):
            suffix = re.search(r"(?<=[x*X])[a-wyzäöüß][a-zäöüß]*$", surface)
            town = gaz.town("AT")[0]
            for _ in range(20):  # a compound ("xxxbach") needs a one-word name
                if not suffix or re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß]+", town):
                    break
                town = gaz.town("AT")[0]
            val = town + (suffix.group() if suffix else "") if label == "location" else \
                f"{re.sub(r'[^a-z]', '', town.lower())}.at"
        elif label == "street":
            val = gaz.surname("AT")
        elif label == "land_register_id":
            val = str(rng.randint(10, 3999)) if rng.random() < 0.6 else f"{rng.randint(10, 2999)}/{rng.randint(1, 40)}"
        elif label == "company_register_number":
            val = f"{rng.randint(10000, 699999)}{rng.choice('abdfghikmpstvwxyz')}"
        elif label == "amount":
            val = f"{rng.randint(50, 99999):,}".replace(",", ".")
        elif label == "other_identifier":
            val = str(rng.randint(1, 999))
        elif label == "case_number" and self.app == "Justiz":
            val = f"{rng.randint(1, 60)} {rng.choice(['Cg', 'C', 'R', 'Hv', 'Bl', 'E', 'P', 'Cga', 'Rs'])} " \
                  f"{rng.randint(1, 400)}/{rng.randint(19, 26)}{rng.choice('abdfghikmpstvwxyz')}"
        elif label == "case_number":
            val = f"{rng.choice(['BHWL', 'BHAM', 'MA35', 'BHKO', 'LPD', 'BH', 'VStV'])}-{rng.randint(1000, 99999)}/" \
                  f"{rng.randint(2019, 2026)}"
        elif label == "license_plate":
            val = f"{rng.choice(['W', 'L', 'G', 'S', 'I', 'K', 'B', 'WU', 'BN', 'KO', 'LL', 'WL'])}-" \
                  f"{rng.randint(100, 99999)}{rng.choice(['', 'A', 'B', 'X', 'TU'])}"
        elif label == "date":
            val = _date_value(rng, style, self.year, self.birth)
        else:  # unknown: a neutral surname keeps the text fluent; the record loses PII coverage
            val = gaz.surname("AT")
        self.memo[key] = val
        return val


_LEGAL_FORM = re.compile(rf"(?:\s(?:[A-ZÄÖÜ][\w\-]*\s){{0,2}}(?:{LEGAL_FORMS}))(?![\w])")
PII_LABELS = ("person", "judge", "lawyer", "address", "date", "organization", "location", "street",
              "land_register_id", "license_plate")


def _candidates(text, app):
    """Placeholder spans (start, end, kind) of every style, longest first on overlap."""
    cands = [(m.start(), m.end(), "date") for m in DATE_PH.finditer(text)]
    cands += [(m.start(), m.end(), "address") for m in ADDR_CODE.finditer(text)]
    cands += [(m.start(), m.end(), "street_address") for m in STREET_PH.finditer(text)
              if re.search(r"\*|XXXX|xxx", m.group())]
    cands += [(m.start(), m.end(), "ph") for m in PH_RUN.finditer(text)]
    if app == "Lvwg":
        cands += [(m.start(), m.end(), "ellipsis") for m in ELLIPSIS_PH.finditer(text)]
        cands += [(m.start(), m.end(), "code") for m in LETTER_CODE.finditer(text)]
        cands += [(m.start(g), m.end(g), "code") for m in PAIR_CODES.finditer(text) for g in (1, 2)]
        cands += [(m.start(), m.end(), "address") for m in CODE_ADDRESS.finditer(text)]
        cands += [(m.start(), m.end(), "town") for m in CODE_PLACE.finditer(text)]
        cands += [(m.start(), m.end(), "code_street") for m in CODE_STREET.finditer(text)]
        cands += [(m.start(), m.end(), "descriptor") for m in DESCRIPTOR_PH.finditer(text)]
    if app in ("Lvwg", "Vwgh", "Vfgh", "Bvwg"):
        cands += [(m.start(1), m.end(1), "initials") for m in INITIALS.finditer(text)]
        cands += [(m.start(1), m.end(1), "town") for m in TOWN_INITIAL.finditer(text)]
        cands += [(m.start(), m.end() - (len(m.group()) - 1), "code") for m in
                  re.finditer(rf"\b[A-ZÄÖÜ](?=(?:\s[A-ZÄÖÜ][\w\-]*){{0,2}}\s(?:{LEGAL_FORMS})(?![\w]))", text)]
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    out, last = [], -1
    for s, e, k in cands:
        if s >= last:
            out.append((s, e, k))
            last = e
    return out


def fill_placeholders(text, gaz, rng, app=None, year=None):
    """Replace placeholders; return (new_text, [(label, start, end, surface)], n_unknown)."""
    filler = Filler(gaz, rng, app, year)
    out, spans, pos, cur, prev, unknown, merged = [], [], 0, 0, None, 0, False
    for s, e, kind in _candidates(text, app):
        if s < pos:  # swallowed by the previous span's extension (legal form, year)
            continue
        surface = text[s:e]
        if kind == "ph" and not re.search(r"\*|XXXX|xx|\.\.\.|…|\[", surface):
            continue
        before, after = text[max(0, s - 60):s], text[e:e + 40]
        gap = text[prev[1]:s] if prev else None
        if kind == "date":
            label = "date"
        elif kind == "address":
            label = ("land_register_id" if re.search(r"\bKG\s$", before) else "location") \
                if TOWN_CODE.fullmatch(surface) else \
                "address" if surface.startswith("Adresse") or surface.count("*") > 4 or "-Ort" in surface \
                or re.search(r"Straße|Gasse|Weg|Platz", surface) \
                else "location"
        elif kind == "code_street":  # with a number, door or town it is the (redacted) address, else a street
            label = "address" if re.search(r"\d|Tür|Top|Stiege|\sin\s|,\s", surface) else "street"
        elif kind == "street_address":
            label = "address"
        elif kind == "descriptor":
            label = DESCRIPTOR_LABEL.get(DESCRIPTOR_PH.match(surface).group(1), "organization")
        elif kind == "town":
            label = "location"
        else:
            label = classify_placeholder(before, after, surface, (prev[0], gap) if prev else None)
            if kind in ("code", "initials") and label in ("unknown", "date", "url", "land_register_id", "case_number",
                                                          "address",
                                                          "license_plate", "street", "company_register_number",
                                                          "other_identifier"):
                label = "person"  # a letter code is a party unless the context says organisation/place
        style = None
        if label == "date":
            style = "daymonth" if re.match(r"^\s?(?:19|20)\d\d\b", after) else \
                "long" if re.search(rf"(?:{MONTHS})\s", text[max(0, s - 400):s + 400]) and kind != "date" else "num"
        if kind == "ellipsis" and label in ("unknown", "amount"):
            continue  # an omission in a quotation ("…"), not a placeholder
        if label == "unknown":
            unknown += 1
        filler.birth = bool(re.search(r"\bgeb(?:\.|oren)", before[-25:]))
        val = filler.value(label, surface, style)
        if label == "amount" and re.match(r"^\s?(?:Jahre|Monate|Wochen|Tage|Uhr|Stunden|Minuten|Prozent|%)", after):
            val = str(rng.randint(1, 23))
        elif label == "amount" and re.search(r"(?:strafen?\svon|Strafrest:?|\d\s(?:und|bis))\s$", before):
            val = rng.choice([f"{rng.randint(2, 30)} Monaten", f"{rng.randint(1, 8)} Jahren", f"{rng.randint(1, 11)} Monaten"])
        if label == "court_town":
            key = next((k for k in ("Oberlandesgericht", "für", "Handelsgericht", "Arbeits", "Bezirksgericht")
                        if k in before[-45:]), "Landesgericht")
            val = rng.choice(COURT_SEATS[key])
        if kind == "descriptor" and label == "organization":  # "[Klinik]" -> "Klinik Haider"
            val = f"{DESCRIPTOR_PH.match(surface).group(1)} {val}"
        if kind == "code_street" and label == "street":  # "C.-platz" -> "Kralikplatz"
            val = filler.value("street", surface) + surface.split("-", 1)[1].lower()
        if label == "date" and style == "daymonth":  # the span covers the surviving year
            m = re.match(r"\s?(?:19|20)\d\d", text[e:])
            val, e = f"{val} {m.group().strip()}", e + m.end()
        if label == "organization":  # the legal form belongs to the span
            form = _LEGAL_FORM.match(text, e)
            if form:
                val += form.group()
                e = form.end()
        # BVwG writes "XXXX , geb." with a space before punctuation
        nxt = e + 1 if re.match(r" [,;.:)]", text[e:e + 2]) and "XXXX" in surface else e
        if prev and prev[0] == "judge" and gap == ", " and _BARE.match(surface) and re.match(r"\s(?:über|als)\b", after) \
                and spans and spans[-1][0] == "person" and spans[-2][0] == "judge":
            # Kärnten "Richterin xxx, xxx über …": the second placeholder is a post-nominal degree of the judge
            degree = rng.choice(["LL.M.", "MBA", "BA", "MSc", "LL.M."])
            unknown -= label == "unknown"
            for _ in range(2):
                lab_, ps, pe, pval = spans.pop()
            out.append(f", {degree}")
            cur += 2 + len(degree)
            spans += [("judge", ps, cur, f"{pval}, {degree}"), ("person", ps, cur, f"{pval}, {degree}")]
            pos, prev = nxt, ("judge", e)
            continue
        if label == "address" and prev and prev[0] == "address" and gap == ", " and _BARE.match(surface) \
                and spans and spans[-1][0] == "address" and ", " in spans[-1][3] and not merged:
            # "***, ***": street, then postcode and town of one address; keep one span
            plab, ps, pe, pval = spans.pop()
            street, town = pval.split(", ", 1)
            out[-1] = street
            cur -= len(pval) - len(street)
            out.append(", " + town)
            cur += 2 + len(town)
            spans.append((plab, ps, cur, f"{street}, {town}"))
            pos, prev, merged = nxt, (label, e), True  # a third "***" is a new address, not a third part
            continue
        merged = False
        out.append(text[pos:s])
        cur += s - pos
        spans.append((label, cur, cur + len(val), val))
        if label in ("judge", "lawyer"):
            spans.append(("person", cur, cur + len(val), val))
        out.append(val)
        cur += len(val)
        pos = nxt
        prev = (label, e)
    out.append(text[pos:])
    spans = [sp for sp in spans if sp[0] not in ("url", "other_identifier", "amount", "court_town")]
    return "".join(out), spans, unknown


_TOWN = r"[A-ZÄÖÜ][\w.\-]*(?:\s(?:an\sder|am|im|bei|ob\sder|in\sder)?\s?[A-ZÄÖÜ][\w.\-]*){0,3}?"
_STREET = rf"[A-ZÄÖÜ][\w.\-]*(?:\s[A-ZÄÖÜ][\w.\-]*){{0,2}}?(?:{_STREET_SUFFIX}|\s(?:Straße|Gasse|Platz|Weg|Ring|Kai))"
_HOUSE = r"\d+[a-z]?(?:-\d+)?(?:/\d+[a-z]?)*(?:/(?:Top\s)?\d+)?"
ADDRESS_CLEAR = re.compile(rf"\b(?:\d{{4}}\s{_TOWN},\s{_STREET}\s{_HOUSE}|{_STREET}\s{_HOUSE},\s\d{{4}}\s{_TOWN})"
                           r"(?=[,;.)\s])")


def _free(taken, s, e):
    return not any(taken[s:e])


def _kopf_end(text):
    """End of the Kopf: the first Spruch/Begründung heading, at most 3000 characters in."""
    m = re.search(r"\n(?:Spruch|Begründung|Entscheidungsgründe|Rechtliche Beurteilung|Gründe:?|Text)\n", text)
    return min(m.start() if m else 3000, 3000)


def rule_spans(text, taken, case_numbers=()):
    """Dates, case numbers, courts, judges (Kopf, signature) and lawyers by rule."""
    spans = []

    def add(label, s, e, extra=()):
        if s < e and _free(taken, s, e):
            for lab in (label,) + tuple(extra):
                spans.append((lab, s, e, text[s:e]))
            for i in range(s, e):
                taken[i] = True

    for m in CASE_RE.finditer(text):
        add("case_number", m.start(), m.end())
    for gz in case_numbers:
        for m in re.finditer(re.escape(gz).replace(r"\ ", r"\s?"), text):
            add("case_number", m.start(), m.end())
    for m in AUTHORITY_GZ.finditer(text):
        add("case_number", m.start(1), m.end(1))
    for m in DATE_RE.finditer(text):
        add("date", m.start(), m.end())
    for m in ADDRESS_CLEAR.finditer(text):
        add("address", m.start(), m.end())
    for m in COURT_RE.finditer(text):
        add("court", m.start(), m.end())
    kopf = text[:_kopf_end(text)]
    for m in JUDGE_INTRO.finditer(kopf):
        role = "person" if re.match(r"Schriftführer", m.group()) else "judge"
        pos = m.end()
        role_word = re.match(rf"(?:{JUDGE_WORDS})\s", kopf[pos:])  # "Vorsitzenden Senatspräsident Dr. X"
        pos += role_word.end() if role_word else 0
        while True:  # a list of names: "Mag. A, Dr. B und Mag. C"
            n = _NAME_RE.match(kopf, pos)
            if not n or not (re.match(DEGREE, n.group()) or re.search(r"\s", n.group())
                             or re.match(r"\s(?:als|und|sowie|in\s|\()|,", kopf[n.end():n.end() + 6])):
                break
            add(role, n.start(), n.end(), () if role == "person" else ("person",))
            sep = _LIST_SEP.match(kopf, n.end())
            if not sep:
                break
            pos = sep.end()
    for m in re.finditer(rf"(?<![\w.])({NAME})(?=\sals\s(?:Einzel)?[Rr]ichter(?:in)?\b)", kopf):
        add("judge", m.start(1), m.end(1), ("person",))  # "erkennt durch Fürst als Einzelrichterin"
    for m in SIGNATURE.finditer(text):
        add("judge", m.start(1), m.end(1), ("person",))
    for m in LAWYER_INTRO.finditer(text):
        names, pos = [], m.end()
        while True:  # "Dr. A, Dr. B, Rechtsanwälte in X" / "Mag. A und MMag. B, Rechtsanwälte"
            n = _NAME_RE.match(text, pos)
            if not n:
                break
            names.append(n)
            sep = re.match(r",\s|\sund\s", text[n.end():n.end() + 5])
            if not sep or LAWYER_AFTER.match(text, n.end()):
                break
            pos = n.end() + sep.end()
        if names and re.match(rf"\s(?:Rechtsanw\w+|Anwalts\w*|Partner)\s?(?:{LEGAL_FORMS})?", text[names[-1].end():]):
            continue  # "SHMP Schwartz Huber-Medek Pallitsch Rechtsanwälte GmbH"
        lawyer = bool(names and (m.group(1) or LAWYER_AFTER.match(text, names[-1].end())))
        for n in names:  # representatives who are not attorneys (parents, legal advisers) are persons
            if re.match(DEGREE, n.group()) or " " in n.group():
                if lawyer:
                    add("lawyer", n.start(), n.end(), ("person",))
                elif not re.search(rf"(?:{LEGAL_FORMS}|&|Partner|Rechtsanw|Anwält|Kanzlei)",
                                   n.group() + text[n.end():n.end() + 80].split(",")[0]):
                    add("person", n.start(), n.end())
    for m in DEGREE_NAME.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        role = "lawyer" if re.search(r"(?:Verteidiger(?:s|in)?|Rechtsanw(?:alt|ältin|älte)|\bRA|Notar(?:in)?|"
                                     r"Verfahrenshelfer(?:s|in)?)\s(?:\w+\s)?$", before) else \
            "judge" if re.search(rf"(?:{JUDGE_WORDS})\s$", before) and not re.search(r"Schriftführer\w*\s$", before) \
            else None
        if not re.match(rf"\s(?:Rechtsanw\w+|Anwalts\w*|Partner)\s?(?:{LEGAL_FORMS})", text[m.end():]):
            add(role or "person", m.start(), m.end(), ("person",) if role else ())
    return spans


def annotate(text, ref, gaz, rng):
    """Return (text, spans); placeholders that could not be classified come back as "unknown" spans."""
    year = int(ref["date"][:4]) if re.match(r"\d{4}", ref.get("date") or "") else None
    text, spans, _ = fill_placeholders(text, gaz, rng, ref.get("app"), year)
    taken = [False] * len(text)
    for lab, s, e, _ in spans:
        if lab != "location":
            for i in range(s, e):
                taken[i] = True
    spans += rule_spans(text, taken, ref.get("case_numbers", ()))
    return text, merge_date_ranges(text, sorted(spans, key=lambda x: (x[1], x[0])))


def to_records(text, spans, ref, max_chars=MAX_CHARS, max_chunks=None):
    """Chunk a decision; a chunk with an unclassified placeholder is not queried for PII labels.

    `max_chunks` keeps only the first chunks. The default keeps all; BVwG country reports
    (hundreds of chunks per decision) are balanced in legalner.build (--cap, --max-per-doc).
    """
    recs = []
    for i, (ctext, cspans) in enumerate(chunk(text, spans, max_chars)[:max_chunks]):
        meta = {"court": ref.get("court"), "app": ref.get("app"), "date": ref.get("date")}
        if any(lab == "unknown" for lab, *_ in cspans):
            meta["uncovered"] = list(PII_LABELS)
        recs.append({
            "id": f"ris/{ref['id']}#{i}", "source": "ris", "doc_id": f"ris/{ref['id']}", "lang": "de",
            "jurisdiction": "AT", "text": ctext,
            "spans": [{"label": lab, "start": s, "end": e, "text": t} for lab, s, e, t in cspans if lab != "unknown"],
            "meta": meta})
    return recs

# ------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--app", default="Justiz", help="Justiz, Vwgh, Vfgh, Bvwg, Lvwg, Dsk …")
    s.add_argument("--court", help="e.g. OGH, OLG, LG (Justiz only)")
    s.add_argument("--bundesland", help="LVwG state, e.g. Kaernten, Niederoesterreich")
    s.add_argument("--since")
    s.add_argument("--until")
    s.add_argument("--pages", type=int, default=1)
    s.add_argument("--per-page", default="OneHundred", choices=list(PAGE_SIZES))
    s.add_argument("--limit", type=int, help="stop after this many references")
    s.add_argument("-o", "--out", default="data/ris/index.jsonl")
    f = sub.add_parser("fetch")
    f.add_argument("index")
    f.add_argument("--cache", default="data/ris/raw")
    f.add_argument("--delay", type=float, default=0.5, help="seconds between downloads")
    c = sub.add_parser("convert")
    c.add_argument("index")
    c.add_argument("--cache", default="data/ris/raw")
    c.add_argument("-o", "--out", default="data/canonical/ris.jsonl")
    c.add_argument("--seed", type=int, default=13)
    c.add_argument("--max-chunks", type=int, default=0,
                   help="chunks kept per decision (0: all; balance courts in legalner.build --cap/--max-per-doc)")
    args = ap.parse_args(argv)

    if args.cmd == "search":
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        known = {json.loads(ln)["id"] for ln in open(out, encoding="utf-8") if ln.strip()} if out.exists() else set()
        with out.open("a", encoding="utf-8") as fh:
            for ref in search(args.app, args.court, args.since, args.until, args.pages, args.per_page,
                              limit=args.limit, bundesland=args.bundesland, skip=known):
                fh.write(json.dumps(ref, ensure_ascii=False) + "\n")
                n += 1
        print(f"{n} references -> {out}")
    elif args.cmd == "fetch":
        refs = [json.loads(ln) for ln in open(args.index, encoding="utf-8") if ln.strip()]
        ok = 0
        for ref in refs:
            try:
                if fetch(ref, args.cache):
                    ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"{ref['id']}: {e}")
            time.sleep(args.delay)
        print(f"fetched {ok}/{len(refs)} into {args.cache}")
    else:
        from legalner.gazetteers import Gazetteer
        rng = random.Random(args.seed)
        gaz = Gazetteer(rng=rng)
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        n_docs = n_recs = 0
        with out.open("w", encoding="utf-8") as fh:
            for ln in open(args.index, encoding="utf-8"):
                if not ln.strip():
                    continue
                ref = json.loads(ln)
                path = next((p for p in (pathlib.Path(args.cache) / f"{ref['id']}.{k}" for k in ("html", "xml"))
                             if p.exists()), None)
                if not path:
                    continue
                text = markup_to_text(path.read_text(encoding="utf-8", errors="replace"))
                text, spans = annotate(text, ref, gaz, rng)
                drift = [sp for sp in spans if text[sp[1]:sp[2]] != sp[3]]
                if drift:  # a rule bug; skip the decision rather than train on shifted spans
                    print(f"{ref['id']}: {len(drift)} spans do not match the text, skipped")
                    continue
                for rec in to_records(text, spans, ref, max_chunks=args.max_chunks or None):
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_recs += 1
                n_docs += 1
        print(f"{n_docs} decisions, {n_recs} records -> {out}")


if __name__ == "__main__":
    main()
