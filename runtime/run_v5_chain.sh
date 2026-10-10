#!/bin/bash
# run_v5_chain.sh — pre-registered v5 run (DECONFOUND_PLAN.md): C2 generation on benchmark/v5, then C3 / C4 derivation
# and scoring with the frozen v4 pipeline (validator, repairer, scorer, prompts and settings unchanged).
# Usage (on the Mac Studio, detached):  cd ~/HRgene-v4/runtime && nohup bash run_v5_chain.sh [models] > /dev/null 2>&1 &
#   [models] comma list, default "gpt-oss:20b,qwen3:8b,qwen3:30b-a3b"; order = run order.
# Output: ../experiments/<YYYYMMDD>-<model-tag>-{C2,C3,C4}-v5/ ; log ../experiments/run-v5.log.
# Safe to re-run: the runner resumes finished requests (receipts.jsonl). The Ollama slot is shared with other research
# lines: never kill or restart ollama; queueing only stretches wall-clock.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
MODELS=${1:-gpt-oss:20b,qwen3:8b,qwen3:30b-a3b}
cd "$(dirname "$0")" || exit 1
D=$(date +%Y%m%d)
E=../experiments
REQ=../benchmark/v5/requests/C2.jsonl
CASES=../benchmark/v5/cases
GOLD=../benchmark/v5/gold
LOG=$E/run-v5.log
[ -f "$REQ" ] || { echo "no $REQ"; exit 1; }
echo "== $(date '+%F %T') v5 chain start models=$MODELS" >> "$LOG"
for M in ${MODELS//,/ }; do
  case "$M" in
    qwen3:8b)      TAG=qwen3-8b;      THINK=false ;;
    gpt-oss:20b)   TAG=gpt-oss-20b;   THINK=low ;;
    qwen3:30b-a3b) TAG=qwen3-30b-a3b; THINK=false ;;
    *) echo "unknown model $M" >> "$LOG"; continue ;;
  esac
  C2=$E/${D}-${TAG}-C2-v5; C3=$E/${D}-${TAG}-C3-v5; C4=$E/${D}-${TAG}-C4-v5
  echo "-- $(date '+%F %T') $M C2 -> $C2" >> "$LOG"
  python3 ollama_runner.py --model "$M" --requests "$REQ" --out "$C2" --num-ctx 16384 --num-predict 6000 \
    --temperature 0 --seed 1 --repeat 1 --think "$THINK" --note "benchmark v5 pre-registered run (144 cases)" >> "$LOG" 2>&1
  echo "-- $(date '+%F %T') $M C2 rc=$?; validate -> $C3" >> "$LOG"
  python3 c34_postprocess.py validate --run "$C2" --cases "$CASES" --out "$C3" >> "$LOG" 2>&1
  echo "-- $(date '+%F %T') repair -> $C4" >> "$LOG"
  python3 c34_postprocess.py repair --run "$C2" --cases "$CASES" --out "$C4" >> "$LOG" 2>&1
  if [ -s "$C4/regen_requests.jsonl" ]; then
    echo "-- $(date '+%F %T') regeneration ($(wc -l < "$C4/regen_requests.jsonl") requests)" >> "$LOG"
    python3 ollama_runner.py --model "$M" --requests "$C4/regen_requests.jsonl" --out "$C4/regen" --num-ctx 16384 --num-predict 6000 \
      --temperature 0 --seed 1 --repeat 1 --think "$THINK" --note "C4 regeneration (v5)" >> "$LOG" 2>&1
  fi
  echo "-- $(date '+%F %T') finalize" >> "$LOG"
  python3 c34_postprocess.py finalize --run "$C2" --cases "$CASES" --out "$C4" >> "$LOG" 2>&1
  python3 ../benchmark/v4/score.py --run "$C2" --cases "$CASES" --gold "$GOLD" >> "$LOG" 2>&1
  python3 ../benchmark/v4/score.py --run "$C3" --cases "$CASES" --gold "$GOLD" >> "$LOG" 2>&1
  python3 ../benchmark/v4/score.py --run "$C4" --c4 --cases "$CASES" --gold "$GOLD" >> "$LOG" 2>&1
  echo "-- $(date '+%F %T') $M done" >> "$LOG"
done
echo "== $(date '+%F %T') v5 chain end" >> "$LOG"
