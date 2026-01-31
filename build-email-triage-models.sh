#!/usr/bin/env bash
set -euo pipefail

# Generates Modelfiles for multiple bases using the shared prompt and creates them in the Ollama container.

PROMPT_FILE="modelfiles/prompt/email-triage.system.txt"
GEN_DIR="modelfiles/generated"

mkdir -p "$GEN_DIR"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Shared prompt not found at $PROMPT_FILE" >&2
  exit 1
fi

readarray -t BASES <<'EOF'
llama3.2:3b,email-triage-llama
deepseek-r1:7b,email-triage-r1
gemma2:2b,email-triage-gemma2
mistral:7b-instruct-q5_K_M,email-triage-mistral7b
EOF

for entry in "${BASES[@]}"; do
  base="${entry%%,*}"
  name="${entry##*,}"
  outfile="$GEN_DIR/${name}.modelfile"
  cat > "$outfile" <<EOF
FROM $base

PARAMETER temperature 0.0
PARAMETER num_ctx 1024
PARAMETER num_predict 80

SYSTEM """
$(cat "$PROMPT_FILE")
"""
EOF
  echo "Generated $outfile"

  # Create model inside the container (modelfiles dir is mounted to /modelfiles)
  docker exec -i ollama ollama create "$name" -f "/modelfiles/generated/${name}.modelfile"
  echo "Created model: $name"
done

echo "All models generated and created. Use OLLAMA_MODEL to select one (e.g., email-triage-r1)."