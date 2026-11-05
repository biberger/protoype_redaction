"""CPU speed benchmark on a fixed text set (the first N gold records), production call, after warm-up.

    python -m legalner.bench out/isel-v3/best --n 150 --threads 4
    python -m legalner.bench out/isel-v3/best --onnx out/isel-v3-pruned-int8/encoder.onnx --id-map out/isel-v3-pruned/id_map.npy
    python -m legalner.bench --flair flair/ner-german-legal          # in an environment with flair installed

Measures characters per second of the service's call (all labels, 96-word chunks); the model is loaded once and the
first 10 texts are run once as warm-up and not timed.
"""
import argparse
import json
import time


def texts(path, n):
    out = []
    for line in open(path, encoding="utf-8"):
        out.append(json.loads(line)["text"])
        if len(out) >= n:
            break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="?")
    ap.add_argument("--data", default="data/canonical/gold_at.jsonl")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--onnx")
    ap.add_argument("--id-map")
    ap.add_argument("--chunk-size", type=int, default=96)
    ap.add_argument("--flair", help="Flair model name instead of a GLiNER2 checkpoint")
    args = ap.parse_args(argv)
    import torch
    torch.set_num_threads(args.threads)
    batch = texts(args.data, args.n)
    if args.flair:
        from flair.data import Sentence
        from flair.models import SequenceTagger
        tagger = SequenceTagger.load(args.flair)

        def run(t):
            tagger.predict(Sentence(t))
    else:
        if args.onnx:
            from legalner.onnx_export import load_with_onnx
            model = load_with_onnx(args.model, args.onnx, args.id_map, threads=args.threads)
        else:
            from gliner2 import AutoExtractor
            model = AutoExtractor.from_pretrained(args.model, map_location="cpu")
            model.eval()
        from legalner.prodeval import predict_cands

        def run(t):
            with torch.inference_mode():
                predict_cands(model, t, args.chunk_size, 0.1)
    for t in batch[:10]:
        run(t)
    t0 = time.time()
    for t in batch:
        run(t)
    dt = time.time() - t0
    chars = sum(len(t) for t in batch)
    print(json.dumps({"model": args.flair or args.model, "onnx": args.onnx, "texts": len(batch), "chars": chars,
                      "seconds": round(dt, 1), "chars_per_s": round(chars / dt), "threads": args.threads}))


if __name__ == "__main__":
    main()
