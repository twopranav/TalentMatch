#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-hf.co/QuantFactory/Qwen2-1.5B-Instruct-GGUF:Q4_K_M}"

ollama serve &
SERVE_PID=$!

# Forward termination signals to the actual server process so
# `docker stop` / compose shutdown doesn't have to wait out its
# default timeout and SIGKILL it.
trap 'kill -TERM "$SERVE_PID"' TERM INT

echo "Waiting for Ollama server to be ready..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

# Idempotent: only pulls if not already present. On a restart with the
# ollama_data volume intact, this is a no-op -- no re-download, no
# dependency on network access at every container start.
if ! ollama list | grep -q "$MODEL"; then
  echo "Pulling $MODEL (first run, or volume was reset)..."
  ollama pull "$MODEL"
else
  echo "$MODEL already present, skipping pull."
fi

wait "$SERVE_PID"