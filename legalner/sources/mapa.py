"""MAPA (EUR-Lex court decisions, CC-BY-4.0), German and French, for evaluation only.

Hub: joelniklaus/mapa (jsonl; tokens, coarse_grained, fine_grained BIO tags).
Mapping onto the canonical schema:

- PERSON -> person, with TITLE/PROFESSION/ROLE tokens trimmed from the edges
  ("Herrn Liberato" -> "Liberato", "Richter E. Juhász" -> "E. Juhász")
- ADDRESS -> address if it has a street, building or postcode part; otherwise each
  city/country/place/territory part is a separate location ("Rom (Italien)")
- DATE -> date only if it has a DAY part (our dates are day-precise)
- ORGANISATION -> organization; it includes courts, so it is scored against
  organization ∪ court (schema.SOURCES["mapa"].eval_merge)
- AMOUNT and the rest: not mapped

    python -m legalner.sources.mapa -o data/canonical/mapa   # writes {train,validation,test}.jsonl
"""
import argparse
import json
import pathlib

from legalner.bio import bio_spans, detokenize

REPO = "joelniklaus/mapa"
SPLITS = ("train", "validation", "test")
LANGS = ("de", "fr")
EDGE_TRIM = {"TITLE", "PROFESSION", "ROLE", "AGE", "MARITAL STATUS", "NATIONALITY", "ETHNIC CATEGORY"}
ADDRESS_PARTS = {"STREET", "BUILDING", "POSTCODE"}
LOCATION_PARTS = {"CITY", "COUNTRY", "PLACE", "TERRITORY"}


def _fine(tag):
    return tag[2:] if tag[:2] in ("B-", "I-") else None


def convert_row(row, split, idx):
    tokens, coarse, fine = row["tokens"], row["coarse_grained"], row["fine_grained"]
    text, off = detokenize(tokens)
    spans = []

    def add(label, a, b):
        s, e = off[a][0], off[b][1]
        spans.append({"label": label, "start": s, "end": e, "text": text[s:e]})

    for typ, a, b in bio_spans(coarse):
        parts = {_fine(t) for t in fine[a:b + 1]} - {None}
        if typ == "PERSON":
            while a <= b and _fine(fine[a]) in EDGE_TRIM:
                a += 1
            while b >= a and _fine(fine[b]) in EDGE_TRIM:
                b -= 1
            if a <= b:
                add("person", a, b)
        elif typ == "ORGANISATION":
            add("organization", a, b)
        elif typ == "DATE" and "DAY" in parts:
            add("date", a, b)
        elif typ == "ADDRESS":
            if parts & ADDRESS_PARTS or not parts:
                add("address", a, b)
            else:
                for ftyp, fa, fb in bio_spans(fine[a:b + 1]):
                    if ftyp in LOCATION_PARTS:
                        add("location", a + fa, a + fb)
    doc = f"mapa/{row['file_name']}"
    return {"id": f"mapa/{split}/{idx}", "source": "mapa", "doc_id": doc, "lang": row["language"],
            "jurisdiction": "EU", "text": text, "spans": spans,
            "meta": {"split": split, "sentence": row["sentence_number"]}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="data/canonical/mapa")
    args = ap.parse_args(argv)
    from huggingface_hub import hf_hub_download
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        n = 0
        with open(hf_hub_download(REPO, f"{split}.jsonl", repo_type="dataset"), encoding="utf-8") as src, \
                (out / f"{split}.jsonl").open("w", encoding="utf-8") as fh:
            for i, line in enumerate(src):
                row = json.loads(line)
                if row["language"] in LANGS:
                    fh.write(json.dumps(convert_row(row, split, i), ensure_ascii=False) + "\n")
                    n += 1
        print(f"{split}: {n} sentences -> {out / f'{split}.jsonl'}")


if __name__ == "__main__":
    main()
