"""Austrian court decisions from the RIS OGD API, pseudonymisation filled from gazetteers.

RIS publishes decisions with party data replaced by placeholders ("A*****",
"Mag. B***** C*****", "*****" in Justiz decisions, "XXXX" at the BVwG). Each
placeholder is classified from its context (person, organization, address,
location, date), replaced by a gazetteer value (consistently within the
document) and labelled. Dates, case numbers, court names, judges in the Kopf
and lawyers after "vertreten durch" are labelled by rule.

Coverage (schema.SOURCES["ris"]) is limited to labels these rules annotate
completely enough; anything else in RIS text (companies and places written in
clear) is left for teacher pseudo-labels.

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

from legalner.tagged import chunk

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


def search(app="Justiz", court=None, since=None, until=None, pages=1, per_page="Hundred", text_only=True):
    """Iterate decision references (full texts only, not Rechtssätze)."""
    params = {"Applikation": app, "DokumenteProSeite": per_page}
    if court:
        params["Gericht"] = court
    if since:
        params["EntscheidungsdatumVon"] = since
    if until:
        params["EntscheidungsdatumBis"] = until
    if text_only:
        params["Dokumenttyp.SucheInEntscheidungstexten"] = "true"
    for page in range(1, pages + 1):
        params["Seitennummer"] = page
        refs, hits = parse_search(json.loads(_get(API + "?" + urllib.parse.urlencode(params))))
        yield from (r for r in refs if not text_only or r["doc_type"] in (None, "Text"))
        if page * {"Ten": 10, "Twenty": 20, "Fifty": 50, "OneHundred": 100, "Hundred": 100}[per_page] >= hits:
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


class _Blocks(html.parser.HTMLParser):
    """Block-level text extraction that works for RIS HTML and risdok XML alike."""
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table", "absatz",
             "ueberschrift", "abschnitt", "titel", "td"}
    SKIP = {"script", "style", "head", "metadaten", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def markup_to_text(markup):
    p = _Blocks()
    p.feed(markup)
    text = "".join(p.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

# ---------------------------------------------------------------- annotation

DEGREE = r"(?:(?:Univ\.-Prof\.|Hon\.-Prof\.|Prof\.|Dr\.|Mag\.|MMag\.|DI|Dipl\.-Ing\.|Ing\.|Mag\.a|Dr\.in|MBA|LL\.M\.|BA|MA|BSc|MSc)(?:\s|$))"
NAME = r"[A-ZÄÖÜ][a-zäöüßéèáíóúčćšžđ'’]+(?:-[A-ZÄÖÜ][a-zäöüßéèáíóúčćšžđ'’]+)?"
PERSON_NAME = rf"{DEGREE}*(?:{NAME}\s){{0,2}}{NAME}"
PH = r"(?:[A-ZÄÖÜ]\*{3,}|\*{3,}|XXXX)"
PH_RUN = re.compile(rf"(?:{DEGREE})*{PH}(?:[ \-]{PH})*")

MONTHS = "Jänner|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
DATE_RE = re.compile(rf"\b(?:[0-3]?\d\.\s?(?:[01]?\d\.\s?(?:19|20)\d\d|(?:{MONTHS})\s(?:19|20)\d\d))\b")
CASE_RE = re.compile(
    r"\b(?:\d{1,2}\s?(?:Ob|Os|ObA|ObS|Fsc|Nc|Nd|R|Cg|C|Cga|Cgs|E|P|Ra|Rs|Hv|Bl|Fss)\s?\d{1,5}/\d{2}[a-z]"
    r"(?:-\d+)?|R[aorsv]\s?\d{4}/\d{2}/\d{4}|[EGUVBW]\s?\d{1,5}/\d{4}(?:-\d+)?|"
    r"[WGIL]\d{3}\s\d{7}-\d(?:/\d+[EZ])?|LVwG-[A-Z0-9\-/]+)")
COURT_RE = re.compile(
    r"\b(?:Oberste[nr]?\s(?:Gerichtshof(?:es|s)?)|OGH|Verfassungsgerichtshof(?:es|s)?|VfGH|"
    r"Verwaltungsgerichtshof(?:es|s)?|VwGH|Bundesverwaltungsgericht(?:es|s)?|BVwG|Bundesfinanzgericht(?:es|s)?|"
    r"Oberlandesgericht(?:es|s)?\s(?:Wien|Graz|Linz|Innsbruck)|OLG\s(?:Wien|Graz|Linz|Innsbruck)|"
    r"Landesgericht(?:es|s)?\sfür\s(?:Zivilrechtssachen|Strafsachen)\s(?:Wien|Graz)|"
    r"Arbeits-\sund\sSozialgericht(?:es|s)?\sWien|Handelsgericht(?:es|s)?\sWien|"
    r"Landesgericht(?:es|s)?\s(?:als\s\w+\s)?(?:" + NAME + r")(?:\s(?:an\sder|am|im)\s" + NAME + r")?|"
    r"Bezirksgericht(?:es|s)?\s(?:für\sHandelssachen\sWien|(?:Innere\sStadt\s)?(?:" + NAME + r")(?:\s(?:an\sder|am|im)\s" + NAME + r")?)|"
    r"Landesverwaltungsgericht(?:es|s)?\s(?:" + NAME + r")|LVwG\s(?:" + NAME + r"))")
JUDGE_INTRO = re.compile(
    r"(?:Senatspräsident(?:in|en)?|Vizepräsident(?:in|en)?|Präsident(?:in|en)?|Hofrät(?:in|innen|e)|Hofrat(?:es)?|"
    r"Richter(?:in|innen)?|Rechtspfleger(?:in)?|Schriftführer(?:in)?|fachkundigen\sLaienrichter(?:n|innen)?|"
    r"Mitglied(?:er)?|Vorsitzende[nr]?|Einzelrichter(?:in)?)(?:\sdes\sObersten\sGerichtshofs)?\s")
_NAME_RE = re.compile(PERSON_NAME)
_LIST_SEP = re.compile(r"(?:,\s|\sund\s|\ssowie\s)(?:die\s|den\s|der\s)?(?:(?:Hofr\w+|Richter\w*)\s)?(?=[A-ZÄÖÜ])")
LAWYER_INTRO = re.compile(r"(?:vertreten\sdurch|Verteidiger(?:in)?:?)\s")

CONTEXT_RULES = [  # (regex on the 60 chars before, regex on the 40 chars after, label)
    (r"(?i)(geboren|geb\.|am|vom|seit)\s*$", r"^\s*[,;)]?", "date"),
    (r"(?i)(wohnhaft|whft\.|Anschrift|Adresse|in|bei)\s*$", r"^,\s*\d{4}", "address"),
    (r"", r"^\s*(GmbH|AG|KG|OG|eU|e\.U\.|Gesellschaft|GesmbH|Ges\.m\.b\.H\.|Privatstiftung|Verein|Bank|Versicherung|"
          r"Immobilien|Bau|Holding|Handels)", "organization"),
    (r"(?i)(in|aus|nach|bei|von)\s*$", r"", "location"),
]


def classify_placeholder(before, after, surface):
    """Guess what a placeholder replaced from its context."""
    if re.match(DEGREE, surface) or re.match(r"^[A-ZÄÖÜ]\*{3,}([ \-][A-ZÄÖÜ]\*{3,})+$", surface):
        return "person"
    for pre, post, label in CONTEXT_RULES:
        if (not pre or re.search(pre, before)) and (not post or re.search(post, after)):
            if label == "date" and not re.match(r"^\s*([,;)]|$)", after):
                continue
            if label == "location" and re.match(r"^[A-ZÄÖÜ]", surface):
                continue
            return label
    return "person" if re.match(r"^[A-ZÄÖÜ]\*", surface) else "address"


_LEGAL_FORM = re.compile(r"\s(?:GmbH|AG|KG|OG|GesmbH|Ges\.m\.b\.H\.|Gesellschaft m\.b\.H\.|e\.U\.|eU|"
                         r"GmbH & Co KG|Privatstiftung)(?![\w])")


class Filler:
    """Consistent replacement values for one document."""

    def __init__(self, gaz, rng):
        self.gaz, self.rng, self.memo = gaz, rng, {}

    def value(self, label, surface):
        key = (label, surface)
        if key in self.memo:
            return self.memo[key]
        degree = " ".join(re.findall(r"(?:Univ\.-Prof\.|Hon\.-Prof\.|Prof\.|Dr\.|Mag\.|MMag\.|DI|Dipl\.-Ing\.|Ing\.)",
                                     surface))
        if label == "person":
            n_parts = len(re.findall(PH, surface))
            name = self.gaz.person("AT") if n_parts != 1 else self.gaz.surname("AT")
            val = f"{degree} {name}".strip()
        elif label == "organization":
            val = f"{self.gaz.surname('AT')}"
        elif label == "address":
            val = self.gaz.address("AT")
        elif label == "location":
            val = self.gaz.town("AT")[0]
        else:  # date
            val = f"{self.rng.randint(1, 28)}.{self.rng.randint(1, 12)}.{self.rng.randint(1950, 2005)}"
        self.memo[key] = val
        return val


def fill_placeholders(text, gaz, rng):
    """Replace placeholders; return (new_text, [(label, start, end, surface)])."""
    filler = Filler(gaz, rng)
    out, spans, pos, cur = [], [], 0, 0
    for m in PH_RUN.finditer(text):
        surface = m.group().strip()
        label = classify_placeholder(text[max(0, m.start() - 60):m.start()], text[m.end():m.end() + 40], surface)
        val = filler.value(label, surface)
        end = m.end()
        if label == "organization":  # the legal form belongs to the span
            form = _LEGAL_FORM.match(text, end)
            if form:
                val += form.group()
                end = form.end()
        out.append(text[pos:m.start()])
        cur += m.start() - pos
        spans.append((label, cur, cur + len(val), val))
        out.append(val)
        cur += len(val)
        pos = end
    out.append(text[pos:])
    return "".join(out), spans


def _free(taken, s, e):
    return not any(taken[s:e])


def rule_spans(text, taken, case_numbers=()):
    """Dates, case numbers, courts, judges (Kopf) and lawyers by rule."""
    spans = []

    def add(label, s, e, extra=()):
        if s < e and _free(taken, s, e):
            for lab in (label,) + tuple(extra):
                spans.append((lab, s, e, text[s:e]))
            for i in range(s, e):
                taken[i] = True

    for gz in case_numbers:
        for m in re.finditer(re.escape(gz).replace(r"\ ", r"\s?"), text):
            add("case_number", m.start(), m.end())
    for m in CASE_RE.finditer(text):
        add("case_number", m.start(), m.end())
    for m in DATE_RE.finditer(text):
        add("date", m.start(), m.end())
    for m in COURT_RE.finditer(text):
        add("court", m.start(), m.end())
    kopf = text[:2500]
    for m in JUDGE_INTRO.finditer(kopf):
        role = "person" if re.match(r"Schriftführer", m.group()) else "judge"
        pos = m.end()
        while True:  # a list of names: "Mag. A, Dr. B und Mag. C"
            n = _NAME_RE.match(kopf, pos)
            if not n:
                break
            add(role, n.start(), n.end(), () if role == "person" else ("person",))
            sep = _LIST_SEP.match(kopf, n.end())
            if not sep:
                break
            pos = sep.end()
    for m in LAWYER_INTRO.finditer(text):
        n = re.match(PERSON_NAME, text[m.end():])
        if n and re.match(r"\s*,?\s*(Rechtsanw(alt|ältin)|Notar|Verteidiger)", text[m.end() + n.end():m.end() + n.end() + 20]):
            add("lawyer", m.end(), m.end() + n.end(), ("person",))
    return spans


def annotate(text, ref, gaz, rng):
    text, spans = fill_placeholders(text, gaz, rng)
    taken = [False] * len(text)
    for _, s, e, _ in spans:
        for i in range(s, e):
            taken[i] = True
    spans += rule_spans(text, taken, ref.get("case_numbers", ()))
    return text, sorted(spans, key=lambda x: (x[1], x[0]))


def to_records(text, spans, ref, max_chars=MAX_CHARS):
    recs = []
    for i, (ctext, cspans) in enumerate(chunk(text, spans, max_chars)):
        recs.append({
            "id": f"ris/{ref['id']}#{i}", "source": "ris", "doc_id": f"ris/{ref['id']}", "lang": "de",
            "jurisdiction": "AT", "text": ctext,
            "spans": [{"label": lab, "start": s, "end": e, "text": t} for lab, s, e, t in cspans],
            "meta": {"court": ref.get("court"), "app": ref.get("app"), "date": ref.get("date")}})
    return recs

# ------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--app", default="Justiz", help="Justiz, Vwgh, Vfgh, Bvwg, Lvwg, Dsk …")
    s.add_argument("--court", help="e.g. OGH, OLG, LG (Justiz only)")
    s.add_argument("--since")
    s.add_argument("--until")
    s.add_argument("--pages", type=int, default=1)
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
    args = ap.parse_args(argv)

    if args.cmd == "search":
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with out.open("a", encoding="utf-8") as fh:
            for ref in search(args.app, args.court, args.since, args.until, args.pages):
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
                for rec in to_records(text, spans, ref):
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_recs += 1
                n_docs += 1
        print(f"{n_docs} decisions, {n_recs} records -> {out}")


if __name__ == "__main__":
    main()
