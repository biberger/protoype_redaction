"""Per-label confidence thresholds, tuned on dev predictions saved with confidences.

    python -m legalner.evaluate out/isel-v3/best dev.jsonl --threshold 0.1 --with-conf --save-preds dev_preds.jsonl
    python -m legalner.thresholds dev.jsonl dev_preds.jsonl -o thresholds.json

For labels that are masked in production (PII) the threshold maximises F2 (recall counts twice: a miss is a leak)
subject to a precision floor; for labels that stay visible (court, date, legal norm, country) it maximises F1.
Labels with too little dev support keep the default.
"""
import argparse
import json

from legalner.build import read_records
from legalner.evaluate import apply_thresholds, score

VISIBLE = {"court", "date", "legal_norm", "country"}
GRID = [round(0.05 * i, 2) for i in range(2, 20)]  # 0.10 .. 0.95


def f_beta(p, r, beta):
    return 0.0 if p + r == 0 else (1 + beta ** 2) * p * r / (beta ** 2 * p + r)


def tune(records, conf, default=0.5, min_support=30, min_precision=0.85):
    by_t = {t: score(records, apply_thresholds(conf, {}, t))["scores"] for t in GRID}
    labels = sorted({k.split("|", 1)[1] for k in by_t[default] if k.startswith("all|") and k != "all|*"})
    chosen, table = {}, {}
    for lab in labels:
        rows = {t: by_t[t].get(f"all|{lab}") for t in GRID}
        if not rows[default] or rows[default]["support"] < min_support:
            continue
        beta = 1 if lab in VISIBLE else 2
        ok = {t: s for t, s in rows.items() if s and (beta == 1 or s["p"] >= min_precision)}
        best = max(ok or rows, key=lambda t: (round(f_beta(rows[t]["p"], rows[t]["r"], beta), 4), -abs(t - default)))
        chosen[lab] = best
        table[lab] = {"support": rows[default]["support"], "beta": beta,
                      "default": {k: rows[default][k] for k in ("p", "r", "f1")},
                      "chosen": {k: rows[best][k] for k in ("p", "r", "f1")}}
    return chosen, table


def load_conf(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        out[d["id"]] = {lab: {(s, e): c for s, e, c in spans} for lab, spans in d["pred"].items()}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", help="canonical JSONL the predictions were made on")
    ap.add_argument("preds", help="--save-preds output written with --with-conf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--min-support", type=int, default=30)
    ap.add_argument("--min-precision", type=float, default=0.85)
    args = ap.parse_args(argv)
    records = list(read_records([args.data]))
    conf_by_id = load_conf(args.preds)
    records = [r for r in records if r["id"] in conf_by_id]
    conf = [conf_by_id[r["id"]] for r in records]
    chosen, table = tune(records, conf, min_support=args.min_support, min_precision=args.min_precision)
    with open(args.out, "w") as fh:
        json.dump(chosen, fh, indent=2, sort_keys=True)
    for lab, t in sorted(chosen.items()):
        row = table[lab]
        print(f"{lab:24s} t={t:.2f} n={row['support']:5d} F{row['beta']}  "
              f"0.50: P={row['default']['p']:.3f} R={row['default']['r']:.3f}  ->  "
              f"P={row['chosen']['p']:.3f} R={row['chosen']['r']:.3f}")


if __name__ == "__main__":
    main()
