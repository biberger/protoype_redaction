"""ONNX export of a GLiNER2 checkpoint's encoder, int8 quantization, and loading with ONNX Runtime.

The encoder (mDeBERTa, ~97 % of the parameters and of the compute) runs in ONNX Runtime; GLiNER2's small heads and
its decoding stay in PyTorch, unchanged. The model calls its encoder in exactly one place
(`BaseExtractorModel`: `self.encoder(input_ids=..., attention_mask=...).last_hidden_state`), so swapping
`model.encoder` for an `OrtEncoder` keeps every other step identical.

    python -m legalner.onnx_export export out/isel-v3/best -o out/isel-v3-onnx/encoder.onnx
    python -m legalner.onnx_export quantize out/isel-v3-onnx/encoder.onnx -o out/isel-v3-int8/encoder.onnx
    python -m legalner.onnx_export parity out/isel-v3/best out/isel-v3-onnx/encoder.onnx data/canonical/gold_at.jsonl
"""
import argparse
import json
import pathlib
import types

import numpy as np


class OrtEncoder:
    """Callable stand-in for the transformers encoder, backed by an ONNX Runtime session.

    id_map: optional int64 array old_token_id -> new_token_id for a vocabulary-pruned encoder."""

    def __init__(self, onnx_path, id_map=None, threads=0):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(onnx_path), so, providers=["CPUExecutionProvider"])
        self.id_map = id_map

    def __call__(self, input_ids=None, attention_mask=None, **_):
        import torch
        ids = input_ids.detach().cpu().numpy().astype(np.int64)
        if self.id_map is not None:
            ids = self.id_map[ids]
        mask = attention_mask.detach().cpu().numpy().astype(np.int64)
        out = self.session.run(["last_hidden_state"], {"input_ids": ids, "attention_mask": mask})[0]
        return types.SimpleNamespace(last_hidden_state=torch.from_numpy(out).to(input_ids.device))

    # the runtime calls .to()/.eval() on submodules in some paths; nothing to move
    def to(self, *a, **k):
        return self

    def eval(self):
        return self


def load_with_onnx(model_dir, onnx_path, id_map_path=None, threads=0):
    """GLiNER2 model whose encoder runs in ONNX Runtime (PyTorch encoder weights are dropped)."""
    import torch
    from gliner2 import AutoExtractor
    model = AutoExtractor.from_pretrained(str(model_dir), map_location="cpu")
    model.eval()
    id_map = np.load(id_map_path) if id_map_path else None
    del model._modules["encoder"]
    object.__setattr__(model, "encoder", OrtEncoder(onnx_path, id_map, threads))
    torch.set_grad_enabled(False)
    return model


def export(model_dir, out, opset=17):
    import torch
    from gliner2 import AutoExtractor
    model = AutoExtractor.from_pretrained(str(model_dir), map_location="cpu")
    model.eval()
    enc = model.encoder

    class Wrap(torch.nn.Module):
        def __init__(self, e):
            super().__init__()
            self.e = e

        def forward(self, input_ids, attention_mask):
            return self.e(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state

    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ids = torch.randint(5, 1000, (2, 64), dtype=torch.long)
    mask = torch.ones_like(ids)
    with torch.no_grad():
        torch.onnx.export(Wrap(enc), (ids, mask), str(out), input_names=["input_ids", "attention_mask"],
                          output_names=["last_hidden_state"], opset_version=opset, dynamo=False,
                          dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                        "last_hidden_state": {0: "batch", 1: "seq"}})
    return out


def quantize(src, out):
    from onnxruntime.quantization import QuantType, quantize_dynamic
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    quantize_dynamic(str(src), str(out), weight_type=QuantType.QInt8, per_channel=True)
    return out


def parity(model_dir, onnx_path, data, n=200, id_map_path=None):
    """Max/mean abs difference of encoder states, PyTorch vs ONNX, on the first n texts' real model inputs."""
    import torch
    from gliner2 import AutoExtractor
    from legalner.build import read_records
    model = AutoExtractor.from_pretrained(str(model_dir), map_location="cpu")
    model.eval()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(model_dir))
    ort_enc = OrtEncoder(onnx_path, np.load(id_map_path) if id_map_path else None)
    texts = [r["text"] for r in list(read_records([data]))[:n]]
    diffs = []
    for t in texts:
        enc = tok(t, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            a = model.encoder(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).last_hidden_state
        b = ort_enc(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).last_hidden_state
        diffs.append((float((a - b).abs().max()), float((a - b).abs().mean())))
    d = np.array(diffs)
    return {"texts": len(texts), "max_abs": float(d[:, 0].max()), "mean_abs": float(d[:, 1].mean())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("model")
    e.add_argument("-o", "--out", required=True)
    q = sub.add_parser("quantize")
    q.add_argument("src")
    q.add_argument("-o", "--out", required=True)
    p = sub.add_parser("parity")
    p.add_argument("model")
    p.add_argument("onnx")
    p.add_argument("data")
    p.add_argument("-n", type=int, default=200)
    p.add_argument("--id-map")
    args = ap.parse_args(argv)
    if args.cmd == "export":
        print(export(args.model, args.out))
    elif args.cmd == "quantize":
        print(quantize(args.src, args.out))
    else:
        print(json.dumps(parity(args.model, args.onnx, args.data, args.n, args.id_map), indent=1))


if __name__ == "__main__":
    main()
