docker compose up -d
# sleep to give ollama time to start
sleep 5
docker exec -i ollama ollama create email-triage -f /modelfiles/email-triage.modelfile