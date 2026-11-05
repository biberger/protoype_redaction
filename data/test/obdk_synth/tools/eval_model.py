"""Evaluate sb-aiss/legalner-v2 on the synthetic OBDK test set.

    python eval_model.py <chunks.jsonl> <docs.jsonl> <app_src_dir> <out_dir>

Two views:
1. model: canonical chunks (<= 1500 chars), all 21 labels, role labels in a second pass,
   exact-match P/R/F1 per label and PII character recall, as legalner.evaluate.
2. app: whole documents, the call GlinerLegalRecognizer makes (one pass, app labels +
   "date of birth", 96-word windows, threshold 0.5) scored under the masking policy:
   courts, dates and legal norms stay visible, countries are dropped, every other gold
   span must be covered by some masked prediction.
Raw predictions are written next to the report so thresholds can be re-scored offline.
"""

import collections
import json
import os
import re
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
import torch
from gliner2 import AutoExtractor
from huggingface_hub import snapshot_download

chunks_path, docs_path, app_src, out_dir = sys.argv[1:5]
sys.path.insert(0, app_src)
from src.processing.recognizers.countries import is_country  # noqa: E402

torch.set_num_threads(int(os.environ.get("THREADS", "4")))
os.makedirs(out_dir, exist_ok=True)

ROLE = ["judge", "lawyer"]
MODEL_LABELS = ["person", "organization", "court", "address", "street", "location", "date", "case_number",
                "bank_account", "social_security_number", "tax_id", "company_register_number", "license_plate",
                "land_register_id", "id_document_number", "other_identifier", "phone_number", "email",
                "legal_norm"]
PII = {"person", "judge", "lawyer", "organization", "address", "street", "location", "bank_account",
       "social_security_number", "tax_id", "company_register_number", "license_plate", "land_register_id",
       "id_document_number", "other_identifier", "phone_number", "email"}
APP_LABELS = MODEL_LABELS[:7] + ["date_of_birth"] + MODEL_LABELS[7:]
UNMASKED = {"date", "court", "legal_norm"}
COUNTRY_LABELS = {"location", "organization"}
BIRTH = re.compile(r"(?i)\bgeb(?:\.|oren)(?:\s+(?:am|in \S+ am))?\s*$")

root = snapshot_download("sb-aiss/legalner-v2", revision="4d87ed49e3eacd5d6b708f3f1e672f0046e07e84",
                         allow_patterns=["best/*"], local_files_only=True)
model = AutoExtractor.from_pretrained(os.path.join(root, "best"), map_location="cpu")
model.eval()


def surface(label):
    return label.replace("_", " ")


def extract(text, labels, long=False):
    names = {surface(lab): lab for lab in labels}
    kw = dict(threshold=0.3, include_spans=True, include_confidence=True)
    if long:
        res = model.extract_entities_long(text, list(names), chunk_size=96, chunk_overlap=24, **kw)
    else:
        res = model.extract_entities(text, list(names), **kw)
    return [[names[n], m["start"], m["end"], round(m["confidence"], 4)]
            for n, ms in res["entities"].items() if n in names for m in ms]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return round(p, 4), round(r, 4), round(2 * p * r / (p + r) if p + r else 0.0, 4)


def read(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


report = {}
with torch.inference_mode():
    # ------------------------------------------------------------ 1. model view
    chunks = read(chunks_path)
    t0 = time.time()
    preds = []
    for rec in chunks:
        preds.append(extract(rec["text"], MODEL_LABELS) + extract(rec["text"], ROLE))
    report["model_seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "preds_model.jsonl"), "w", encoding="utf-8") as fh:
        for rec, p in zip(chunks, preds):
            fh.write(json.dumps({"id": rec["id"], "pred": p}, ensure_ascii=False) + "\n")

    for thr in (0.4, 0.5):
        counts = collections.defaultdict(lambda: [0, 0, 0])
        g_pii = h_pii = 0
        for rec, p in zip(chunks, preds):
            gold = collections.defaultdict(set)
            for s in rec["spans"]:
                gold[s["label"]].add((s["start"], s["end"]))
            pred = collections.defaultdict(set)
            for lab, a, b, c in p:
                if c >= thr:
                    pred[lab].add((a, b))
            for lab in MODEL_LABELS + ROLE:
                g, q = gold.get(lab, set()), pred.get(lab, set())
                for key in (lab, "*"):
                    counts[key][0] += len(g & q)
                    counts[key][1] += len(q - g)
                    counts[key][2] += len(g - q)
            pc = {i for spans in pred.values() for a, b in spans for i in range(a, b)}
            gc = {i for lab, spans in gold.items() if lab in PII for a, b in spans for i in range(a, b)}
            g_pii += len(gc)
            h_pii += len(gc & pc)
        report[f"model@{thr}"] = {
            "pii_char_recall": round(h_pii / g_pii, 4),
            "labels": {lab: dict(zip(("p", "r", "f1"), prf(*c)), support=c[0] + c[2]) for lab, c in counts.items()},
        }

    # ------------------------------------------------------------ 2. app view
    docs = read(docs_path)
    t0 = time.time()
    chars = 0
    app_preds = []
    for rec in docs:
        app_preds.append(extract(rec["text"], APP_LABELS, long=True))
        chars += len(rec["text"])
    sec = time.time() - t0
    report["app_seconds"] = round(sec, 1)
    report["app_chars_per_second"] = round(chars / sec)
    with open(os.path.join(out_dir, "preds_app.jsonl"), "w", encoding="utf-8") as fh:
        for rec, p in zip(docs, app_preds):
            fh.write(json.dumps({"id": rec["id"], "pred": p}, ensure_ascii=False) + "\n")

    for thr in (0.4, 0.5):
        g_all = p_all = hit = 0
        missed = collections.Counter()
        total = collections.Counter()
        missed_examples = collections.defaultdict(list)
        over_masked = collections.Counter()
        for rec, p in zip(docs, app_preds):
            text = rec["text"]
            # the app masks birth dates (zero-shot "date of birth"); gold only says "date"
            gold = [("date_of_birth" if s["label"] == "date" else s["label"], s["start"], s["end"])
                    for s in rec["spans"]
                    if (s["label"] not in UNMASKED or (s["label"] == "date" and BIRTH.search(text[max(0, s["start"] - 25):s["start"]])))
                    and not (s["label"] in COUNTRY_LABELS and is_country(text[s["start"]:s["end"]]))]
            masked = [(lab, a, b) for lab, a, b, c in p if c >= thr and lab not in UNMASKED
                      and not (lab in COUNTRY_LABELS and is_country(text[a:b]))]
            gc = {i for _, a, b in gold for i in range(a, b)}
            pc = {i for _, a, b in masked for i in range(a, b)}
            g_all += len(gc)
            p_all += len(pc)
            hit += len(gc & pc)
            for lab, a, b in gold:
                total[lab] += 1
                if not set(range(a, b)) <= pc:
                    missed[lab] += 1
                    if len(missed_examples[lab]) < 15:
                        missed_examples[lab].append(text[max(0, a - 30):a] + "[[" + text[a:b] + "]]" + text[b:b + 20])
            # masked text that is gold court/date/norm: over-masking of what must stay visible
            visible = {i for s in rec["spans"] if s["label"] in UNMASKED for i in range(s["start"], s["end"])}
            for lab, a, b in masked:
                if set(range(a, b)) & visible and not set(range(a, b)) & gc:
                    over_masked[lab] += 1
        report[f"app@{thr}"] = {
            "mask_char_recall": round(hit / g_all, 4),
            "mask_char_precision": round(hit / p_all, 4),
            "span_miss_rate": {lab: f"{missed[lab]}/{total[lab]}" for lab in sorted(total)},
            "over_masked_visible_spans": dict(over_masked),
            "missed_examples": dict(missed_examples),
        }

with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
for key in ("model@0.5", "app@0.5"):
    r = report[key]
    print(key, {k: v for k, v in r.items() if k not in ("labels", "missed_examples")})
for lab, s in sorted(report["model@0.5"]["labels"].items()):
    print(f"  {lab:24s} P={s['p']:.3f} R={s['r']:.3f} F1={s['f1']:.3f} n={s['support']}")
