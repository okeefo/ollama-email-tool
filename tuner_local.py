import os
import time
import csv
import requests
import json

from tuning_common import STORAGE_DIR, RESULTS_DIR, get_latest_emails, parse_eml

OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "email-triage"


def classify_email(sender, subject, snippet):
    """Call local Ollama model using the custom 'email-triage' modelfile."""
    prompt = f"From: {sender}\nSubject: {subject}\nBody Snippet: {snippet}"
    try:
        r = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_thread": 8,
                    "num_predict": 128,
                    "num_ctx": 1024,
                },
            },
            timeout=60,
        )
        r.raise_for_status()
        response_data = r.json()
        model_output = json.loads(response_data.get("response", "{}"))
        return model_output.get("is_promotional", False), model_output.get(
            "reason", "N/A"
        )
    except requests.exceptions.Timeout:
        return False, "LLM Timeout (Still thinking...)"
    except Exception as e:
        return False, f"LLM Error: {str(e)}"


def run_tuning_session(storage_dir: str = None, count: int = 50):
    storage_dir = storage_dir or STORAGE_DIR
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if not os.environ.get("OLLAMA_KEEP_ALIVE") and count <= 100:
        print("[Tip] Set OLLAMA_KEEP_ALIVE=-1 to keep the model loaded between runs.")

    ts = time.strftime("%Y%m%d-%H%M%S")
    results_path = os.path.join(RESULTS_DIR, f"tuning_{ts}.csv")

    files = get_latest_emails(storage_dir, count=count)
    print(f"\n--- Tuning Session (Local): Reviewing {len(files)} Newest Emails ---")

    total_start_time = time.time()
    ai_total = 0.0
    ai_count = 0

    with open(results_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "seq_id",
                "message_id",
                "status",
                "subject",
                "parse_sec",
                "ai_sec",
                "reason",
            ]
        )

        for filename in files:
            path = os.path.join(storage_dir, filename)
            try:
                seq_id = int(os.path.splitext(filename)[0])
            except Exception:
                seq_id = -1

            start_parse = time.time()
            sender, subject, snippet, message_id = parse_eml(path)
            parse_duration = time.time() - start_parse

            start_ai = time.time()
            is_promo, reason = classify_email(sender, subject, snippet)
            ai_duration = time.time() - start_ai

            status = "[DELETE]" if is_promo else "[ KEEP ]"
            ai_total += ai_duration
            ai_count += 1
            ai_avg = ai_total / ai_count if ai_count else 0.0

            print(
                f"{status} | {subject[:40]:<40} | {ai_duration:4.1f}s (avg {ai_avg:4.1f}s) | {reason}"
            )

            writer.writerow(
                [
                    seq_id,
                    message_id,
                    status,
                    subject,
                    f"{parse_duration:.3f}",
                    f"{ai_duration:.3f}",
                    reason,
                ]
            )

        if ai_count:
            ai_final_avg = ai_total / ai_count
            writer.writerow(
                [
                    "",
                    "",
                    "SUMMARY",
                    "",
                    "",
                    f"{ai_final_avg:.3f}",
                    "average AI decision time",
                ]
            )

    total_duration = time.time() - total_start_time
    print("\n" + "=" * 80)
    print(
        f"Session Complete: {len(files)} emails in {total_duration:.1f}s "
        f"(Avg: {total_duration/max(1,len(files)):.1f}s per email)"
    )
    print(f"Saved results to: {results_path}")
    print("=" * 80)
