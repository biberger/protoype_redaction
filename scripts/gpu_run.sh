#!/usr/bin/env bash
# First GPU run: environment, data, build, smoke run, full run, evaluation.
#
#   bash scripts/gpu_run.sh setup     # venv with CUDA torch + gliner2 (once)
#   bash scripts/gpu_run.sh data      # regenerate data/canonical (RIS fetch ~25 min, HF downloads)
#   bash scripts/gpu_run.sh build     # data/build/v1 (mix 40/30/15/15, gold excluded, validated)
#   bash scripts/gpu_run.sh smoke     # 20 steps, checks memory and speed
#   bash scripts/gpu_run.sh train     # full run -> out/v1
#   bash scripts/gpu_run.sh eval      # fine-tuned model and baselines on gold / test sets
#
# Instead of `data`, data/canonical/ (129 MB) can be copied from a machine that already has it.
# Needs: an NVIDIA GPU with bf16 (Ampere or newer, >= 24 GB), Python 3.10+, access to huggingface.co,
# data.bka.gv.at and ogd.ris.bka.gv.at.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
BUILD=${BUILD:-data/build/v1}
RUN=${RUN:-out/v1}
CUDA=${CUDA:-cu124}

case "${1:-}" in
setup)
  python3 -m venv .venv
  .venv/bin/pip install -q --index-url "https://download.pytorch.org/whl/$CUDA" torch
  .venv/bin/pip install -q gliner2 transformers numpy sentencepiece huggingface_hub pyarrow pytest
  $PY -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0)); \
          print('bf16', torch.cuda.is_bf16_supported())"
  $PY -m pytest -q
  ;;
data)
  mkdir -p data/canonical
  $PY -m legalner.tagged data/synthetic/raw -o data/canonical/synthetic_v1.jsonl --source synthetic_v1
  $PY -m legalner.tagged data/synthetic/raw_v2 -o data/canonical/synthetic.jsonl --source synthetic
  $PY -m legalner.tagged data/synthetic/raw_v3 -o data/canonical/synthetic_v3.jsonl --source synthetic
  $PY -m legalner.tagged data/synthetic/raw_v4 -o data/canonical/synthetic_v4.jsonl --source synthetic
  if [ -d data/synthetic/raw_v5 ]; then
    $PY -m legalner.tagged data/synthetic/raw_v5 -o data/canonical/synthetic_v5.jsonl --source synthetic
  fi
  $PY -m legalner.tagged data/synthetic/raw_v6 -o data/canonical/synthetic_v6.jsonl --source synthetic_eu
  $PY -m legalner.tagged data/eurlex/corrected -o data/canonical/eurlex.jsonl --source eurlex
  $PY -m legalner.tagged data/mapa_v2/corrected -o data/canonical/mapa_v2.jsonl --source mapa_v2
  $PY -m legalner.sources.ler -o data/canonical/ler
  $PY -m legalner.sources.replay -o data/canonical/replay.jsonl --max-per-set 5000
  $PY -m legalner.sources.mapa -o data/canonical/mapa
  # the RIS cache of the first run is committed (10 MB); fetch only downloads what is missing from it
  [ -d data/ris/raw ] || tar -C data/ris -xJf data/ris/raw.tar.xz
  $PY -m legalner.sources.ris fetch data/ris/index.jsonl --cache data/ris/raw --delay 0.3
  $PY -m legalner.sources.ris convert data/ris/index.jsonl --cache data/ris/raw -o data/canonical/ris.jsonl
  $PY -m legalner.goldset export
  ;;
build)
  $PY -m legalner.build \
    data/canonical/synthetic_v1.jsonl data/canonical/synthetic.jsonl data/canonical/synthetic_v3.jsonl \
    data/canonical/synthetic_v4.jsonl $(ls data/canonical/synthetic_v5.jsonl 2>/dev/null) \
    data/canonical/synthetic_v6.jsonl data/canonical/eurlex.jsonl \
    data/canonical/ris.jsonl data/canonical/replay.jsonl \
    data/canonical/ler/*.jsonl data/canonical/mapa/*.jsonl data/canonical/mapa_v2.jsonl data/canonical/gold_at.jsonl \
    --exclude-docs data/gold/at/doc_ids.txt \
    --max-per-doc ris=20 --cap ris:Bundesverwaltungsgericht=800 --source-copies synthetic_eu=3 \
    --mix ler=0.39,synthetic=0.3,ris=0.145,replay=0.145,eurlex=0.02 \
    --validate -o "$BUILD" > /dev/null
  $PY -c "import json; m = json.load(open('$BUILD/manifest.json')); \
          print({k: m[k] for k in ('train', 'dev', 'test', 'train_share', 'validate')})"
  ;;
smoke)
  $PY -m legalner.train "$BUILD" -o out/smoke --max-steps 20 --eval-steps 10 --precision bf16
  ;;
train)
  $PY -m legalner.train "$BUILD" -o "$RUN" --epochs 3 --batch-size 8 --grad-accum 4 \
    --encoder-lr 1e-5 --task-lr 5e-4 --eval-steps 500 --precision bf16 ${WANDB:+--wandb "$WANDB"}
  ;;
eval)
  mkdir -p out/eval
  for model in "$RUN/best" fastino/gliner2.5-multi-v1 fastino/gliner2-privacy-filter-PII-multi; do
    name=$(basename "$model")
    $PY -m legalner.evaluate "$model" data/canonical/gold_at.jsonl --out "out/eval/gold_$name.json" \
      --save-preds "out/eval/preds_gold_$name.jsonl"
    $PY -m legalner.evaluate "$model" data/canonical/mapa_v2.jsonl --out "out/eval/mapa2_$name.json" \
      --save-preds "out/eval/preds_mapa2_$name.jsonl"
    $PY -m legalner.evaluate "$model" "$BUILD/test.canonical.jsonl" --max-per-source 2000 \
      --out "out/eval/test_$name.json" --save-preds "out/eval/preds_test_$name.jsonl"
  done
  ;;
*)
  sed -n '2,13p' "$0"; exit 1
  ;;
esac
