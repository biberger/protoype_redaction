"""Vocabulary pruning of the mDeBERTa embedding table (192M of the encoder's 278M parameters).

The tokenizer stays unchanged; `id_map.npy` maps every original token id to its row in the pruned table (dropped
tokens -> [UNK]) and `OrtEncoder` applies it before the ONNX call. Two ways to choose the kept tokens:

- `script`: every token in Latin (U+0000-U+024F), Cyrillic or Greek script plus symbols: nothing a German, French or
  English document needs is dropped (168k of 250k rows);
- `corpus`: tokens seen in the training split (plus label names and all special/added tokens), optionally with a
  `script` fallback; measure `oov` on the held-out sets before using it.

    python -m legalner.vocab_prune count -o out/vocab/train_counts.npy
    python -m legalner.vocab_prune oov out/vocab/keep_corpus.npy
    python -m legalner.vocab_prune build out/isel-v3/best --keep out/vocab/keep_script.npy -o out/isel-v3-pruned
"""
import argparse
import glob
import json
import pathlib
import unicodedata

import numpy as np

EVAL = ["data/canonical/gold_at.jsonl", "data/canonical/mapa_v2.jsonl",
        "data/test/obdk_synth/obdk_synth_test.docs.jsonl", "data/test/regression/regression.jsonl"]


def tokenizer(model_dir="out/isel-v3/best"):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(model_dir))


def script_keep(tok):
    def ok(piece):
        for ch in piece.replace("▁", ""):
            if ord(ch) <= 0x024F:
                continue
            if unicodedata.name(ch, "").startswith(("CYRILLIC", "GREEK")):
                continue
            if not ch.isalpha() and ord(ch) < 0x3000:
                continue
            return False
        return True
    return {i for p, i in tok.get_vocab().items() if ok(p)}


def always_keep(tok):
    from legalner.prodeval import PROD_QUERY
    from legalner.schema import LABELS
    keep = set(tok.get_added_vocab().values()) | set(tok.all_special_ids)
    names = set(PROD_QUERY)
    for k, v in LABELS.items():
        names |= {k, k.replace("_", " ")} | set(getattr(v, "de", ()) or ()) | set(getattr(v, "fr", ()) or ())
        names.add(v.description)
    for n in names:
        keep |= set(tok(n, add_special_tokens=False)["input_ids"])
    return keep


def count(tok, paths, batch=256):
    counts = np.zeros(len(tok), dtype=np.int64)
    texts = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            d = json.loads(line)
            if d.get("split", "train") == "train":
                texts.append(d["text"])
    for i in range(0, len(texts), batch):
        for ids in tok(texts[i:i + batch], add_special_tokens=False)["input_ids"]:
            np.add.at(counts, ids, 1)
    return counts


def oov(tok, keep, paths=EVAL):
    keep = set(int(x) for x in keep)
    tot = miss = 0
    for p in paths:
        for line in open(p, encoding="utf-8"):
            ids = tok(json.loads(line)["text"], add_special_tokens=False)["input_ids"]
            tot += len(ids)
            miss += sum(1 for i in ids if i not in keep)
    return {"tokens": tot, "oov": miss, "rate": miss / max(tot, 1)}


def build(model_dir, keep, out):
    """Pruned encoder exported to ONNX + id_map.npy (original id -> new id; dropped -> [UNK])."""
    import torch
    from gliner2 import AutoExtractor
    from legalner.onnx_export import export_model
    tok = tokenizer(model_dir)
    keep = sorted(set(int(x) for x in keep) | {tok.unk_token_id, tok.pad_token_id})
    model = AutoExtractor.from_pretrained(str(model_dir), map_location="cpu")
    model.eval()
    emb = model.encoder.embeddings.word_embeddings
    new = torch.nn.Embedding(len(keep), emb.weight.shape[1], padding_idx=keep.index(tok.pad_token_id))
    with torch.no_grad():
        new.weight.copy_(emb.weight[torch.tensor(keep)])
    model.encoder.embeddings.word_embeddings = new
    id_map = np.full(emb.weight.shape[0], keep.index(tok.unk_token_id), dtype=np.int64)
    id_map[np.array(keep)] = np.arange(len(keep))
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "id_map.npy", id_map)
    export_model(model, out / "encoder.onnx", vocab=len(keep))
    return {"rows": len(keep), "of": int(emb.weight.shape[0])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("-o", "--out", required=True)
    c.add_argument("--data", nargs="+", default=sorted(glob.glob("data/export/legalner-at-data/data/*.jsonl")))
    k = sub.add_parser("keep", help="write keep sets: script, corpus (min count), corpus+script")
    k.add_argument("counts")
    k.add_argument("--min-count", type=int, default=1)
    k.add_argument("-o", "--out-dir", default="out/vocab")
    o = sub.add_parser("oov")
    o.add_argument("keep")
    b = sub.add_parser("build")
    b.add_argument("model")
    b.add_argument("--keep", required=True)
    b.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    tok = tokenizer()
    if args.cmd == "count":
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        np.save(args.out, count(tok, args.data))
        print("saved", args.out)
    elif args.cmd == "keep":
        counts = np.load(args.counts)
        base = always_keep(tok)
        sets = {"script": script_keep(tok) | base,
                "corpus": set(np.nonzero(counts >= args.min_count)[0].tolist()) | base}
        sets["corpus_script"] = sets["corpus"] | sets["script"]
        pathlib.Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        for name, s in sets.items():
            np.save(pathlib.Path(args.out_dir, f"keep_{name}.npy"), np.array(sorted(s)))
            print(name, len(s))
    elif args.cmd == "oov":
        print(json.dumps(oov(tok, np.load(args.keep))))
    else:
        print(build(args.model, np.load(args.keep), args.out))


if __name__ == "__main__":
    main()
