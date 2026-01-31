docker compose up -d
# sleep to give ollama time to start
sleep 5

# Optional: create a selected model from generated modelfiles
# Usage: MODEL_NAME=email-triage-r1 ./start-model.sh
MODEL_NAME="${MODEL_NAME:-email-triage}"
MODELFILE_HOST="modelfiles/generated/${MODEL_NAME}.modelfile"

if [ -f "$MODELFILE_HOST" ]; then
	echo "Creating model '$MODEL_NAME' from generated modelfile..."
	docker exec -i ollama ollama create "$MODEL_NAME" -f "/modelfiles/generated/${MODEL_NAME}.modelfile"
else
	echo "Generated modelfile not found for '$MODEL_NAME'. Falling back to email-triage.modelfile."
	docker exec -i ollama ollama create email-triage -f /modelfiles/email-triage.modelfile
fi