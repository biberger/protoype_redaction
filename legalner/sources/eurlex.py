"""EU court texts from CELLAR (EUR-Lex): CJEU and General Court judgments and AG opinions, German and French.

Unlabelled real text for the EU gap found in the MAPA analysis (docs/PLAN.md). The chunks are pre-annotated
by a model (legalner.pretag) and corrected by agents to the GENERATION.md conventions, then parsed with
`legalner.tagged --source eurlex`.

    python -m legalner.sources.eurlex list --per-type 40 --since 2019 -o data/eurlex/index.jsonl
    python -m legalner.sources.eurlex fetch data/eurlex/index.jsonl --cache data/eurlex/raw
    python -m legalner.sources.eurlex chunks data/eurlex/index.jsonl --cache data/eurlex/raw \
        --exclude data/canonical/mapa/*.jsonl --per-doc 4 -o data/eurlex/chunks.jsonl

Hosts: publications.europa.eu (SPARQL endpoint and content negotiation; eur-lex.europa.eu itself answers bots
with an empty 202). EU documents may be reused with attribution (Commission Decision 2011/833/EU).
"""
import argparse
import hashlib
import html
import json
import pathlib
import random
import re
import time
import urllib.parse
import urllib.request

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
RESOURCE = "https://publications.europa.eu/resource/celex/{celex}"
LANGS = {"de": "deu", "fr": "fra"}
# CELEX sector 6 document types: CJ judgment of the Court, CC AG opinion, TJ judgment of the General Court
TYPES = ("CJ", "CC", "TJ")


def _get(url, headers=None, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "legalner/1 (research)", **(headers or {})})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def list_celex(doc_type, since, until, limit):
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex WHERE {{ ?w cdm:resource_legal_id_celex ?celex .
FILTER(REGEX(STR(?celex), "^6({'|'.join(str(y) for y in range(since, until + 1))}){doc_type}")) }} LIMIT {limit}"""
    url = SPARQL + "?" + urllib.parse.urlencode({"query": q})
    data = json.loads(_get(url, {"Accept": "application/sparql-results+json"}))
    ids = {b["celex"]["value"] for b in data["results"]["bindings"]}
    return sorted(i for i in ids if re.fullmatch(rf"6\d{{4}}{doc_type}\d{{4}}", i))  # no _SUM/_INF/_RES variants


class _Paragraphs:
    """Text of the <p> elements of a CELLAR XHTML document (footnote markers dropped)."""
    TAG = re.compile(r"<(/?)(p|br|sup|span|a|em|i|b|strong|td|tr|table|div)\b[^>]*>", re.I)

    @staticmethod
    def extract(xhtml):
        body = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", xhtml)
        body = re.sub(r"(?is)<sup\b[^>]*>.*?</sup>", "", body)  # footnote markers "( *1 )"
        paras = []
        for m in re.finditer(r"(?is)<p\b[^>]*>(.*?)</p>", body):
            t = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
            t = re.sub(r"[ \t ]+", " ", t).strip()
            t = t.replace("‑", "-")  # non-breaking hyphen in case numbers (C‑311/19)
            if t:
                paras.append(t)
        return paras


def chunk(paras, max_chars=1200):
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + 1 + len(p) > max_chars:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{p}" if cur else p
        while len(cur) > max_chars:  # very long paragraph: split at a sentence end
            cut = cur.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 3 else max_chars
            out.append(cur[:cut].strip())
            cur = cur[cut:].strip()
    if cur:
        out.append(cur)
    return out


def _norm(s):
    return re.sub(r"\W+", "", s.lower())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--per-type", type=int, default=40)
    a.add_argument("--since", type=int, default=2019)
    a.add_argument("--until", type=int, default=2024)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("-o", "--out", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("index")
    f.add_argument("--cache", required=True)
    f.add_argument("--delay", type=float, default=0.5)
    c = sub.add_parser("chunks")
    c.add_argument("index")
    c.add_argument("--cache", required=True)
    c.add_argument("--exclude", nargs="*", default=[], help="canonical JSONL whose sentences must not occur (MAPA)")
    c.add_argument("--per-doc", type=int, default=4, help="chunks per document and language (first chunk always)")
    c.add_argument("--one-lang", action="store_true",
                   help="one language per document, alternating (more documents per chunk budget)")
    c.add_argument("--seed", type=int, default=7)
    c.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "list":
        rng = random.Random(args.seed)
        rows = []
        for t in TYPES:
            ids = list_celex(t, args.since, args.until, 5000)
            for celex in sorted(rng.sample(ids, min(args.per_type, len(ids)))):
                rows.append({"celex": celex, "type": t})
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows)
        print(f"{len(rows)} documents -> {args.out}")
    elif args.cmd == "fetch":
        cache = pathlib.Path(args.cache)
        cache.mkdir(parents=True, exist_ok=True)
        rows = [json.loads(ln) for ln in open(args.index)]
        n = 0
        for r in rows:
            for lang, code in LANGS.items():
                path = cache / f"{r['celex']}_{lang}.xhtml"
                if path.exists():
                    continue
                try:
                    data = _get(RESOURCE.format(celex=r["celex"]),
                                {"Accept": "application/xhtml+xml", "Accept-Language": code})
                except Exception as e:  # not every document exists in both languages
                    print(f"{r['celex']} {lang}: {e}")
                    continue
                path.write_bytes(data)
                n += 1
                time.sleep(args.delay)
        print(f"fetched {n} files into {cache}")
    else:
        rng = random.Random(args.seed)
        seen = set()
        for path in args.exclude:
            for ln in open(path, encoding="utf-8"):
                t = json.loads(ln)["text"]
                if len(t) > 40:
                    seen.add(hashlib.sha1(_norm(t).encode()).hexdigest())
        rows = [json.loads(ln) for ln in open(args.index)]
        out, skipped = [], 0
        for k, r in enumerate(rows):
            for lang in ([list(LANGS)[k % 2]] if args.one_lang else LANGS):
                path = pathlib.Path(args.cache) / f"{r['celex']}_{lang}.xhtml"
                if not path.exists():
                    continue
                paras = _Paragraphs.extract(path.read_text(encoding="utf-8", errors="ignore"))
                if any(hashlib.sha1(_norm(p).encode()).hexdigest() in seen for p in paras if len(p) > 40):
                    skipped += 1
                    continue
                chunks = chunk(paras)
                if not chunks:
                    continue
                pick = [0] + sorted(rng.sample(range(1, len(chunks)), min(args.per_doc - 1, len(chunks) - 1)))
                for i in pick:
                    out.append({"id": f"eurlex/{r['celex']}_{lang}/{i}", "doc_id": f"eurlex/{r['celex']}_{lang}",
                                "lang": lang, "celex": r["celex"], "type": r["type"], "chunk": i, "text": chunks[i]})
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(o, ensure_ascii=False) + "\n" for o in out)
        print(f"{len(out)} chunks from {len({o['doc_id'] for o in out})} documents -> {args.out} "
              f"({skipped} documents skipped: overlap with --exclude)")


if __name__ == "__main__":
    main()
