"""GLiNER v1 replay data, to keep zero-shot ability while fine-tuning.

Only these two Apache-2.0 sets are used (decision in docs/PLAN.md; Pile-NER is excluded):

- urchade/pile-mistral-v0.1          English web text, open label set (≈19.7k docs)
- urchade/synthetic-pii-ner-mistral-v1  synthetic PII texts in en/fr/de/it/es/pt (≈19.6k docs)

Format: {"tokenized_text": [...], "ner": [[first_tok, last_tok_inclusive, label], ...]}.
Labels are free text; each record queries its own labels plus `--negatives` labels
sampled from the label pool of the same dataset (as in GLiNER v1 training).

    python -m legalner.sources.replay -o data/canonical/replay.jsonl --max-per-set 5000
"""
import argparse
import collections
import json
import pathlib
import random

from legalner.bio import detokenize

SETS = {"pile-mistral": "urchade/pile-mistral-v0.1",
        "synthetic-pii": "urchade/synthetic-pii-ner-mistral-v1"}
MAX_TOKENS = 384  # GLiNER v1 data is pre-chunked; longer docs are cut into windows


def guess_lang(tokens):
    """Cheap stopword vote; the PII set mixes languages without a language field."""
    words = {t.lower() for t in tokens[:200]}
    votes = {
        "de": {"der", "die", "und", "ist", "nicht", "mit", "von", "den", "ein", "eine"},
        "fr": {"le", "la", "les", "et", "est", "des", "une", "du", "pour", "dans"},
        "it": {"il", "di", "che", "è", "per", "una", "della", "con", "sono", "gli"},
        "es": {"el", "los", "que", "y", "es", "una", "por", "con", "para", "del"},
        "pt": {"o", "os", "que", "e", "é", "uma", "com", "não", "para", "do"},
        "en": {"the", "and", "is", "of", "to", "in", "that", "with", "for", "was"},
    }
    return max(votes, key=lambda k: len(words & votes[k]))


def windows(tokens, ner, size=MAX_TOKENS):
    """Cut a long token list into windows; drop entities crossing a cut."""
    for start in range(0, max(len(tokens), 1), size):
        end = min(start + size, len(tokens))
        ents = [(a - start, b - start, lab) for a, b, lab in ner if a >= start and b < end]
        yield tokens[start:end], ents


def convert(name, data, rng, negatives, max_docs=0):
    pool = sorted({lab.strip().lower() for d in data for *_, lab in d["ner"] if lab.strip()})
    order = list(range(len(data)))
    rng.shuffle(order)
    out = []
    for idx in order:
        d = data[idx]
        for w, (tokens, ents) in enumerate(windows(d["tokenized_text"], d["ner"])):
            if not tokens:
                continue
            text, off = detokenize(tokens)
            spans, seen = [], set()
            for a, b, lab in ents:
                lab = lab.strip().lower()
                if not lab or b < a or (a, b, lab) in seen:
                    continue
                seen.add((a, b, lab))
                s, e = off[a][0], off[b][1]
                spans.append({"label": lab, "start": s, "end": e, "text": text[s:e]})
            present = sorted({s["label"] for s in spans})
            negs = [lab for lab in rng.sample(pool, min(len(pool), negatives * 3)) if lab not in present][:negatives]
            if not present and not negs:
                continue
            doc = f"replay/{name}/{idx}"
            out.append({"id": f"{doc}#{w}", "source": "replay", "doc_id": doc, "lang": guess_lang(tokens),
                        "jurisdiction": "XX", "text": text, "spans": spans,
                        "meta": {"set": name, "query_labels": present + negs}})
        if max_docs and len({r["doc_id"] for r in out}) >= max_docs:
            break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="data/canonical/replay.jsonl")
    ap.add_argument("--max-per-set", type=int, default=0, help="documents per set (0 = all)")
    ap.add_argument("--negatives", type=int, default=3, help="sampled negative labels per record")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args(argv)
    from huggingface_hub import hf_hub_download
    rng = random.Random(args.seed)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for name, repo in SETS.items():
            with open(hf_hub_download(repo, "data.json", repo_type="dataset"), encoding="utf-8") as f:
                data = json.load(f)
            recs = convert(name, data, rng, args.negatives, args.max_per_set)
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            langs = collections.Counter(r["lang"] for r in recs)
            print(f"{name}: {len(recs)} records, langs {dict(langs.most_common())}")


if __name__ == "__main__":
    main()
