import os
import time
import csv
import email
from email import policy
import requests
import json

OLLAMA_API_URL = 'http://127.0.0.1:11434/api/generate'
# Hard-pin model to custom modelfile
OLLAMA_MODEL = 'email-triage'

# Global paths
STORAGE_DIR = os.environ.get('EMAIL_STORAGE_DIR', '/srv/storage/docker/email_data/raw_emails')
RESULTS_DIR = os.environ.get('TUNING_RESULTS_DIR', './tuning_results')

def get_latest_emails(directory, count=50):
    """Returns the filenames of the newest emails based on sequence ID."""
    files = [f for f in os.listdir(directory) if f.endswith('.eml')]
    # Sort numerically descending (Highest SeqID = Newest)
    files.sort(key=lambda x: int(x.split('.')[0]), reverse=True)
    return files[:count]

def parse_eml(filepath):
    """Extracts basic info from an eml file for the LLM, including Message-ID."""
    try:
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        
        sender = msg.get('from', '(Unknown)')
        subject = msg.get('subject', '(No Subject)')
        message_id = msg.get('Message-ID', '(No Message-ID)')
        
        # Extract plain text body snippet
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors='ignore')
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors='ignore')
        
        # Clean up whitespace and limit snippet
        snippet = body.strip().replace('\n', ' ')[:500]
        return sender, subject, snippet, message_id
    except Exception as e:
        return "Error", "Error", str(e), "(Error)"

            
def classify_email(sender, subject, snippet):
    """Simplified call using the custom 'email-triage' modelfile."""

    prompt = f"From: {sender}\nSubject: {subject}\nBody Snippet: {snippet}"

    try:
        #Model context window: Added num_ctx: 1024 to the Ollama options in tuner.py for tighter memory use and potential CPU cache benefits.

        r = requests.post(OLLAMA_API_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "num_thread": 8,
                "num_predict": 128,
                "num_ctx": 1024 
            }
        }, timeout=60)

        r.raise_for_status()
        response_data = r.json()
        model_output = json.loads(response_data.get('response', '{}'))
        return model_output.get('is_promotional', False), model_output.get('reason', 'N/A')

    except requests.exceptions.Timeout:
        return False, "LLM Timeout (Still thinking...)"

    except Exception as e:
        return False, f"LLM Error: {str(e)}"

def run_tuning_session(storage_dir: str = None, count: int = 50):
    storage_dir = storage_dir or STORAGE_DIR

    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Hint: keep model resident for small batches
    if not os.environ.get('OLLAMA_KEEP_ALIVE') and count <= 100:
        print("[Tip] Set OLLAMA_KEEP_ALIVE=-1 to keep the model loaded between runs.")

    # Timestamped, human-sortable filename
    ts = time.strftime('%Y%m%d-%H%M%S')
    results_path = os.path.join(RESULTS_DIR, f'tuning_{ts}.csv')

    # Select the newest N emails based on sequence ID
    files = get_latest_emails(storage_dir, count=count)
    print(f"\n--- Tuning Session: Reviewing {len(files)} Newest Emails ---")

    total_start_time = time.time()

    # Track running AI decision time for console, and final average for file
    ai_total = 0.0
    ai_count = 0

    # Write header and rows to a CSV file while printing to console
    with open(results_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'seq_id', 'message_id', 'status', 'subject', 'parse_sec', 'ai_sec', 'reason'
        ])

        for filename in files:
            path = os.path.join(storage_dir, filename)

            # numeric sequence id from filename
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

            status = '[DELETE]' if is_promo else '[ KEEP ]'

            # Update running average for console output
            ai_total += ai_duration
            ai_count += 1
            ai_avg = ai_total / ai_count if ai_count else 0.0

            # Console output with current running average
            print(f"{status} | {subject[:40]:<40} | {ai_duration:4.1f}s (avg {ai_avg:4.1f}s) | {reason}")

            # File output
            writer.writerow([
                seq_id, message_id, status, subject, f"{parse_duration:.3f}", f"{ai_duration:.3f}", reason
            ])

        # Append a single summary row with final average AI decision time
        if ai_count:
            ai_final_avg = ai_total / ai_count
            writer.writerow(['', '', 'SUMMARY', '', '', f"{ai_final_avg:.3f}", 'average AI decision time'])

    total_duration = time.time() - total_start_time
    print("\n" + "=" * 80)
    print(
        f"Session Complete: {len(files)} emails in {total_duration:.1f}s "
        f"(Avg: {total_duration/len(files):.1f}s per email)"
    )
    print(f"Saved results to: {results_path}")
    print("=" * 80)