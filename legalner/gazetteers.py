"""Build and load the name/place gazetteers (compact TSVs in data/gazetteers/).

Sources (all CC0):
- first names: WGND 2.0 (WIPO World Gender Name Dictionary, Harvard Dataverse
  doi:10.7910/DVN/MSEGSJ), file wgnd_2_0_name-gender-code.csv
- surnames: Wikidata family names (P734) of people by citizenship (P27),
  counted locally (aggregating in SPARQL times out)
- places: Wikidata municipalities with postal code, and streets, for AT/DE/CH

    python -m legalner.gazetteers first-names data/gazetteers/raw/wgnd_2_0_name-gender-code.csv
    python -m legalner.gazetteers surnames [--codes europe]
    python -m legalner.gazetteers places

Countries cover the target jurisdictions plus the origins of the largest immigrant
groups, so generated names do not collapse onto a few German ones.
"""
import argparse
import collections
import csv
import pathlib
import random
import re
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path("data/gazetteers")
SPARQL = "https://query.wikidata.org/sparql"
UA = "legalner-gazetteer/0.1 (research; contact via github biberger/protoype_redaction)"

# ISO code -> Wikidata item
COUNTRIES = {
    "AT": "Q40", "DE": "Q183", "CH": "Q39", "FR": "Q142", "BE": "Q31", "LU": "Q32", "LI": "Q347",
    "IT": "Q38", "TR": "Q43", "RS": "Q403", "BA": "Q225", "HR": "Q224", "PL": "Q36", "CZ": "Q213",
    "SK": "Q214", "HU": "Q28", "RO": "Q218", "UA": "Q212", "SY": "Q858", "IR": "Q794", "AF": "Q889",
    "NG": "Q1033", "SN": "Q1041", "MA": "Q1028", "DZ": "Q262", "PT": "Q45", "ES": "Q29",
    # 2026-11: the rest of Europe, so name coverage is not limited to the target jurisdictions
    "NL": "Q29999", "IE": "Q27", "GB": "Q145", "DK": "Q756617", "SE": "Q34", "NO": "Q20", "FI": "Q33", "EE": "Q191",
    "LV": "Q211", "LT": "Q37", "SI": "Q215", "BG": "Q219", "GR": "Q41", "ME": "Q236", "MK": "Q221", "AL": "Q222",
    "MT": "Q233", "CY": "Q229",
}
EUROPE = {"AT", "DE", "CH", "FR", "BE", "LU", "LI", "IT", "RS", "BA", "HR", "PL", "CZ", "SK", "HU", "RO", "UA", "PT",
          "ES", "NL", "IE", "GB", "DK", "SE", "NO", "FI", "EE", "LV", "LT", "SI", "BG", "GR", "ME", "MK", "AL", "MT",
          "CY", "TR"}
# distinctive surnames of prominent Austrian/German politicians: a fictitious "Vester Van der Bellen" reads as the
# federal president, so generated persons never get them (common surnames like Kurz or Huber stay)
PROMINENT = frozenset({"Van der Bellen", "Nehammer", "Kickl", "Strache", "Gusenbauer", "Faymann", "Mikl-Leitner",
                       "Babler", "Schallenberg", "Klestil", "Waldheim", "Kreisky", "Vranitzky", "Schüssel", "Haider",
                       "Fischer-Kreisky", "Edtstadler", "Gewessler", "Kogler", "Doskozil", "Merkel", "Scholz",
                       "Steinmeier", "Söder", "Habeck", "Lindner-Merz", "Merz"})
MAX_FIRST = 3000
MAX_SURNAMES = 2000
# European countries get larger lists: name-swap augmentation (build.py) cycles through all of them
MAX_FIRST_EUROPE = 8000
MAX_SURNAMES_EUROPE = 4000


def _title(name):
    return re.sub(r"(^|[\s\-'’])(\w)", lambda m: m.group(1) + m.group(2).upper(), name)


def build_first_names(wgnd_csv, out=OUT / "first_names.tsv", seed=13):
    """Per country up to MAX_FIRST names with gender M/F (random sample, WGND has no frequencies)."""
    rng = random.Random(seed)
    by = collections.defaultdict(set)
    with open(wgnd_csv, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name, code, g = row["name"].strip(), row["code"], row["gender"]
            if code in COUNTRIES and g in ("M", "F") and re.fullmatch(r"[^\W\d_]+(?:[-'’ ][^\W\d_]+)?", name) \
                    and len(name) >= 2:
                by[code].add((_title(name), g))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("country\tname\tgender\n")
        for code in COUNTRIES:
            names = sorted(by[code])
            cap = MAX_FIRST_EUROPE if code in EUROPE else MAX_FIRST
            if len(names) > cap:
                names = sorted(rng.sample(names, cap))
            for name, g in names:
                fh.write(f"{code}\t{name}\t{g}\n")
            print(f"{code}: {len(names)} first names")


def sparql(query, retries=3):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query})
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return list(csv.DictReader(r.read().decode("utf-8").splitlines()))
        except Exception as e:  # noqa: BLE001 - retry on timeouts / 429 / 5xx
            if attempt == retries - 1:
                raise
            print(f"  retry after {e}")
            time.sleep(5 * (attempt + 1))


def labels(qids, langs=("mul", "de", "fr", "en")):
    """QID -> label, preferring the order of `langs`."""
    out = {}
    qids = list(qids)
    for i in range(0, len(qids), 400):
        values = " ".join(f"wd:{q}" for q in qids[i:i + 400])
        rows = sparql(f"SELECT ?x ?l WHERE {{ VALUES ?x {{ {values} }} ?x rdfs:label ?l . "
                      f"FILTER(LANG(?l) IN ({', '.join(repr(x) for x in langs)})) }}")
        best = {}
        for r in rows:
            q = r["x"].rsplit("/", 1)[1]
            # the CSV result has no language tag; keep the first Latin-script label
            if q not in best and re.fullmatch(r"[A-Za-zÀ-ɏ'’ \-]+", r["l"]):
                best[q] = r["l"]
        out.update(best)
    return out


def build_surnames(out=OUT / "surnames.tsv", codes=None):
    """Surnames per country; with `codes`, only those countries are (re)built and the others kept from `out`."""
    keep = []
    if codes and out.exists():
        keep = [ln for ln in out.read_text(encoding="utf-8").splitlines()[1:] if ln.split("\t")[0] not in codes]
    with out.open("w", encoding="utf-8") as fh:
        fh.write("country\tname\tcount\n")
        fh.writelines(ln + "\n" for ln in keep)
        for code, q in COUNTRIES.items():
            if codes and code not in codes:
                continue
            rows = sparql(f"SELECT ?fn WHERE {{ ?p wdt:P27 wd:{q}; wdt:P734 ?fn . }} LIMIT 300000")
            counts = collections.Counter(r["fn"].rsplit("/", 1)[1] for r in rows)
            top = [qid for qid, _ in counts.most_common(MAX_SURNAMES_EUROPE if code in EUROPE else MAX_SURNAMES)]
            names = labels(top)
            n = 0
            for qid in top:
                if qid in names:
                    fh.write(f"{code}\t{names[qid]}\t{counts[qid]}\n")
                    n += 1
            print(f"{code}: {n} surnames (from {len(rows)} persons)")


PLACE_COUNTRIES = {"AT": "Q40", "DE": "Q183", "CH": "Q39"}


def build_places(out_dir=OUT):
    """Municipalities with postcode, and street names, for AT/DE/CH."""
    with (out_dir / "municipalities.tsv").open("w", encoding="utf-8") as fh:
        fh.write("country\tname\tpostcode\n")
        for code, q in PLACE_COUNTRIES.items():
            rows = sparql(f"SELECT ?m ?pc WHERE {{ ?m wdt:P17 wd:{q}; wdt:P281 ?pc; "
                          f"wdt:P31/wdt:P279* wd:Q15284 . }} LIMIT 60000")
            pcs = {}
            for r in rows:
                pc = r["pc"].strip()
                if re.fullmatch(r"\d{4,5}", pc):
                    pcs.setdefault(r["m"].rsplit("/", 1)[1], pc)
            names = labels(pcs)
            for qid, pc in pcs.items():
                if qid in names:
                    fh.write(f"{code}\t{names[qid]}\t{pc}\n")
            print(f"{code}: {sum(q in names for q in pcs)} municipalities")
    with (out_dir / "streets.tsv").open("w", encoding="utf-8") as fh:
        fh.write("country\tname\n")
        for code, q in PLACE_COUNTRIES.items():
            rows = sparql(f"SELECT ?s WHERE {{ ?s wdt:P31 wd:Q79007; wdt:P17 wd:{q} . }} LIMIT 40000")
            qids = [r["s"].rsplit("/", 1)[1] for r in rows]
            names = sorted(set(labels(qids).values()))
            names = [n for n in names if re.search(r"(?i)(stra(ss|ß)e|gasse|weg|platz|allee|ring|zeile|"
                                                   r"damm|ufer|steig|markt|promenade|kai|lände)$", n)]
            for n in names:
                fh.write(f"{code}\t{n}\n")
            print(f"{code}: {len(names)} streets")


_CYR = dict(zip("абвгґдеєжзиіїйклмнопрстуфхцчшщьюяыэёъ",
                ["a", "b", "w", "h", "g", "d", "e", "je", "sch", "s", "y", "i", "ji", "j", "k", "l", "m", "n", "o",
                 "p", "r", "s", "t", "u", "f", "ch", "z", "tsch", "sch", "schtsch", "", "ju", "ja", "y", "e", "jo", ""]))


_GRK = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώϊϋΐΰ",
                ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o", "p", "r", "s", "s", "t", "y",
                 "f", "ch", "ps", "o", "a", "e", "i", "i", "o", "y", "o", "i", "y", "i", "y"]))


def transliterate(name):
    """Cyrillic and Greek -> Latin transliteration ("Олена" -> "Olena", "Σωκρατης" -> "Sokratis"), as Austrian
    documents write such names."""
    name = name.replace("ου", "ou").replace("Ου", "Ou").replace("ΟΥ", "OU")
    out = []
    for c in name:
        t = _CYR.get(c.lower(), _GRK.get(c.lower()))
        out.append(c if t is None else (t.capitalize() if c.isupper() else t))
    return "".join(out)


class Gazetteer:
    """Draws from the TSVs: names by country/gender, municipalities, streets.

    Names come from shuffled decks (without replacement until a list is used up), so a wave of generated
    documents or a name-swap pass covers every name of a country before any repeats."""

    def __init__(self, root=OUT, rng=None):
        self.rng = rng or random.Random()
        self._decks = {}
        self.first = collections.defaultdict(list)
        self.last = collections.defaultdict(list)
        self.towns = collections.defaultdict(list)
        self.streets = collections.defaultdict(list)
        root = pathlib.Path(root)
        for row in self._rows(root / "first_names.tsv"):
            self.first[(row["country"], row["gender"])].append(row["name"])
        rare = collections.defaultdict(list)
        for row in self._rows(root / "surnames.tsv"):
            # names borne by a single person in Wikidata are often noise (foreign spouses, typos)
            (self.last if int(row["count"]) >= 2 else rare)[row["country"]].append(row["name"])
        for c in list(self.last):  # distinctive surnames of prominent public figures are not used for fake persons
            self.last[c] = [n for n in self.last[c] if n not in PROMINENT]
        for c, names in rare.items():
            if len(self.last[c]) < 300:
                self.last[c] += names
        for row in self._rows(root / "municipalities.tsv"):
            if row["country"] == "DE" and len(row["postcode"]) != 5:
                continue  # pre-1993 four-digit West German postcodes in Wikidata
            self.towns[row["country"]].append((row["name"], row["postcode"]))
        for row in self._rows(root / "streets.tsv"):
            self.streets[row["country"]].append(row["name"])

    @staticmethod
    def _rows(path):
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def origin(self, home):
        """Mostly the home country, sometimes a common immigrant origin."""
        others = [c for c in COUNTRIES if c != home and self.last[c]]
        return home if self.rng.random() < 0.7 or not others else self.rng.choice(others)

    def _draw(self, key, pool):
        deck = self._decks.get(key)
        if not deck:
            deck = self._decks[key] = list(pool)
            self.rng.shuffle(deck)
        return deck.pop()

    def first_name(self, country, gender):
        key = (country, gender) if self.first[(country, gender)] else ("AT", gender)
        return self._draw(("first",) + key, self.first[key])

    def last_name(self, country):
        key = country if self.last[country] else "AT"
        return self._draw(("last", key), self.last[key])

    def person(self, home="AT", gender=None):
        c = self.origin(home)
        gender = gender or self.rng.choice("MF")
        return transliterate(f"{self.first_name(c, gender)} {self.last_name(c)}")

    def surname(self, home="AT"):
        return transliterate(self.last_name(self.origin(home)))

    def town(self, country="AT"):
        return self.rng.choice(self.towns[country])

    def address(self, country="AT"):
        street = self.rng.choice(self.streets[country])
        name, pc = self.town(country)
        door = f"/{self.rng.randint(1, 24)}" if country == "AT" and self.rng.random() < 0.5 else ""
        number = min(250, int(self.rng.lognormvariate(2.3, 0.9)) + 1)
        return f"{street} {number}{door}, {pc} {name}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["first-names", "surnames", "places"])
    ap.add_argument("wgnd", nargs="?", help="WGND name-gender-code CSV (first-names only)")
    ap.add_argument("--codes", help="surnames: comma-separated countries to rebuild (others kept), 'europe' for EUROPE")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.what == "first-names":
        build_first_names(args.wgnd)
    elif args.what == "surnames":
        codes = None
        if args.codes:
            codes = EUROPE if args.codes == "europe" else set(args.codes.split(","))
        build_surnames(codes=codes)
    else:
        build_places()


if __name__ == "__main__":
    main()
