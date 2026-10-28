"""German Legal Entity Recognition dataset (Leitner et al. 2019, CC-BY-4.0).

Hub: elenanereiss/german-ler (parquet; columns tokens, ner, coarse-ner).
Sentences from German federal court decisions, 19 fine-grained classes.

    python -m legalner.sources.ler -o data/canonical/ler   # writes {train,validation,test}.jsonl
"""
import argparse
import json
import pathlib

from legalner.bio import bio_to_record

REPO = "elenanereiss/german-ler"
SPLITS = ("train", "validation", "test")

# LER fine class -> canonical labels (role classes also emit person)
LABEL_MAP = {
    "PER": ("person",), "RR": ("judge", "person"), "AN": ("lawyer", "person"),
    "LD": ("location",), "ST": ("location",), "LDS": ("location",), "STR": ("street",),
    "ORG": ("organization",), "UN": ("organization",), "INN": ("organization",),
    "GRT": ("court",), "MRK": ("brand",),
    "GS": ("legal_norm",), "VO": ("legal_norm",), "EUN": ("legal_norm",), "VS": ("legal_norm",),
    "VT": ("contract",), "RS": ("case_citation",), "LIT": ("literature",),
}


def convert_row(tokens, tags, split, idx):
    text, spans = bio_to_record(list(tokens), list(tags))
    out = []
    for typ, s, e in spans:
        for label in LABEL_MAP[typ]:
            out.append({"label": label, "start": s, "end": e, "text": text[s:e]})
    return {"id": f"ler/{split}/{idx}", "source": "ler", "doc_id": f"ler/{split}/{idx}",
            "lang": "de", "jurisdiction": "DE", "text": text, "spans": out,
            "meta": {"split": split}}


def load_split(split):
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq
    path = hf_hub_download(REPO, f"data/{split}-00000-of-00001.parquet", repo_type="dataset")
    table = pq.read_table(path, columns=["tokens", "ner"])
    return zip(table.column("tokens").to_pylist(), table.column("ner").to_pylist())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="data/canonical/ler")
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        n = 0
        with (out / f"{split}.jsonl").open("w", encoding="utf-8") as fh:
            for i, (tokens, tags) in enumerate(load_split(split)):
                fh.write(json.dumps(convert_row(tokens, tags, split, i), ensure_ascii=False) + "\n")
                n += 1
        print(f"{split}: {n} sentences -> {out / f'{split}.jsonl'}")


if __name__ == "__main__":
    main()
