#!/usr/bin/env bash
# RunPod start script: data + code from a private HF dataset repo, smoke, train, eval,
# results to a private HF model repo, then the pod stops itself.
#
# Env: HF_TOKEN, HF_REPO (dataset repo with build/ and code.tar.gz), HF_OUT (model repo),
#      optional STEPS="smoke train eval", MAX_HOURS (self-stop watchdog, default 7.5);
#      for local tests: CHECK_CUDA=0, STOP_SLEEP=0.
# Start command on the pod:
#   bash -c 'curl -fsSL -H "Authorization: Bearer $HF_TOKEN" \
#     https://huggingface.co/datasets/$HF_REPO/resolve/main/pod_run.sh -o /pod_run.sh && bash /pod_run.sh'
set -uo pipefail
W=${WORKDIR:-/workspace/run}
LOG=$W/logs
STEPS=${STEPS-"smoke train eval"}
mkdir -p "$LOG"
exec > >(tee -a "$LOG/pod.log") 2>&1
export HF_HUB_ENABLE_HF_TRANSFER=0 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false
stamp() { date -u +%FT%TZ; }
note() { echo "[$(stamp)] $*" | tee -a "$LOG/progress.log"; }

stop_pod() {
  note "stopping pod ${RUNPOD_POD_ID:-?}"
  upload_logs || true
  if [ -n "${RUNPOD_POD_ID:-}" ]; then
    runpodctl stop pod "$RUNPOD_POD_ID" || runpodctl remove pod "$RUNPOD_POD_ID" || true
  fi
  sleep "${STOP_SLEEP:-600}"   # never fall through to a restart loop
}

upload_logs() {
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader >> "$LOG/gpu.log" 2>/dev/null
  python - <<PY
from huggingface_hub import HfApi
import os
HfApi().upload_folder(folder_path="$LOG", path_in_repo="logs", repo_id=os.environ["HF_OUT"],
                      repo_type="model", commit_message="progress")
PY
}

descendants() { local c; for c in $(pgrep -P "$1"); do descendants "$c"; echo "$c"; done; }
trap 'kill $(descendants $$) 2>/dev/null' EXIT
# watchdog: hard wall-clock cap, independent of the main job
( sleep "$(python3 -c "print(int(float('${MAX_HOURS:-7.5}')*3600))")"; note "WATCHDOG: MAX_HOURS reached"; stop_pod ) &
# progress uploader every 15 min
( sleep 120; while true; do upload_logs > /dev/null 2>&1 || true; sleep 900; done ) &

fail() { note "FAILED: $*"; stop_pod; exit 1; }

note "start; steps=$STEPS; gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python -m pip install -q "torch==2.6.0" --index-url https://download.pytorch.org/whl/cu124 || fail "torch install"
python -m pip install -q "gliner2==2.1.0" "transformers==5.22.0" sentencepiece "huggingface_hub>=1.0" pyarrow numpy \
  safetensors protobuf || fail "pip install"
# the image's torchvision/torchaudio are built for its own torch and break transformers' imports
python -m pip uninstall -y -q torchvision torchaudio
python -c "from gliner2 import AutoExtractor; from gliner2.training import ExtractorTrainer" || fail "import gliner2"
[ "${CHECK_CUDA:-1}" = 0 ] || python -c "import torch; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(); print(torch.__version__, torch.cuda.get_device_name(0))" \
  || fail "no cuda/bf16"

cd "$W"
python - <<PY || fail "download"
from huggingface_hub import snapshot_download
import os
snapshot_download(os.environ["HF_REPO"], repo_type="dataset", local_dir="dl")
PY
mkdir -p repo && tar -xzf dl/code.tar.gz -C repo && mkdir -p repo/data/build repo/data/canonical \
  && cp -r dl/build/v1 repo/data/build/v1 && cp dl/canonical/gold_at.jsonl repo/data/canonical/ || fail "unpack"
cd repo
# gpu_run.sh expects .venv/bin/python; point it at the system interpreter
mkdir -p .venv/bin && ln -sf "$(command -v python)" .venv/bin/python
note "data ready: $(wc -l < data/build/v1/train.jsonl) train records"

run_step() {  # name
  note "step $1 begin"
  local t0=$(date +%s)
  ( while sleep 60; do nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | sed "s/^/$(date -u +%T) /"; done ) \
    >> "$LOG/gpu_$1.log" 2>&1 &
  local mon=$!
  bash scripts/gpu_run.sh "$1" > "$LOG/$1.log" 2>&1
  local rc=$?
  kill $mon 2>/dev/null
  note "step $1 end rc=$rc in $(( ($(date +%s)-t0)/60 )) min; peak mem $(sort -t, -k2 -n "$LOG/gpu_$1.log" | tail -1)"
  grep -E "'loss'|train_loss|eval_loss|samples/s|it/s" "$LOG/$1.log" | tail -5 >> "$LOG/progress.log"
  return $rc
}

for s in $STEPS; do
  run_step "$s" || fail "step $s"
  if [ "$s" = smoke ]; then
    python - "$LOG/smoke.log" <<'PY' | tee -a "$LOG/progress.log"
import re, sys
txt = open(sys.argv[1]).read()
ls = [float(x) for x in re.findall(r"loss[\"']?\s*[:=]\s*([0-9.]+)", txt)]
print("smoke losses:", ls[:40])
PY
    upload_logs || true
  fi
  if [ "$s" = train ]; then
    python - <<PY || note "WARN upload of model failed"
from huggingface_hub import HfApi
import os
api = HfApi()
for p in ("out/v1/best",):
    api.upload_folder(folder_path=p, path_in_repo="best", repo_id=os.environ["HF_OUT"], commit_message="best checkpoint")
for f in ("train_result.json",):
    if os.path.exists("out/v1/" + f):
        api.upload_file(path_or_fileobj="out/v1/" + f, path_in_repo=f, repo_id=os.environ["HF_OUT"])
PY
  fi
  if [ "$s" = eval ]; then
    python -c "
from huggingface_hub import HfApi; import os
HfApi().upload_folder(folder_path='out/eval', path_in_repo='eval', repo_id=os.environ['HF_OUT'], commit_message='eval')" \
      || note "WARN eval upload failed"
  fi
done
note "ALL DONE"
stop_pod
