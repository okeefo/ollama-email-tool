import os
import time
import csv
import email
from email import policy
import requests
import json

OLLAMA_API_URL = 'http://127.0.0.1:11434/api/generate'
#OLLAMA_MODEL = 'mistral:7b-instruct-q5_K_M'
OLLAMA_MODEL = 'gemma2:2b' # A smaller, faster model for tuning sessions

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
    """The 'Aggressive' Prompt to catch news briefings and marketing."""
    prompt = f"""
    Analyze this email (older than 3 months). 
    
    FLAG AS TRUE (DELETE) if it is:
    - Promotional/Marketing/Sales
    - News briefings, daily digests, or automated news updates (e.g. "Labour market weakens", "Trump sues the BBC")
    - Generic automated notifications
    - a recruiter or job alert email
    - a recruiter and i have haven't replied or shown interest in the last 3 months  
    
    
    FLAG AS FALSE (KEEP) if it is:
    - IMPORTANT: If an email is a RECORD of money spent or an individual financial transaction, always KEEP it, even if it is automated.
    - Financial transactions, bank statements, or pension updates
    - A personal/direct human-to-human conversation
    - A formal receipt, invoice, or order confirmation (e.g., Amazon orders, MiPermit parking, train tickets, SaaS subscriptions)
    - Critical account security or legal alerts
    - Important updates from services I actively use
    - Medical related emails from my doctor, hospital, or health insurance provider
    - if its from family, friends, or colleagues
    - if its from myself (my own email address or variants of it. keithpyle@gmail okeefo@gmail.com, xxkeefxx@gmail.com and okeefo@live.co.uk)
    - HMRC correspondence regarding tax or self-assessment
    - if its form my pension provider or financial institution regarding my accounts or statements
    

    EMAIL DATA:
    From: {sender}
    Subject: {subject}
    Body Snippet: {snippet}

    OUTPUT ONLY VALID JSON: {{"is_promotional": true/false, "reason": "short reason"}}
    """
    
    try:
        # Timeout set to 60 to allow for CPU inference time
        r = requests.post(OLLAMA_API_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,  # Zero creativity = faster decisions
                "num_thread": 8,     # Use all your Beelink cores
                "num_predict": 128   # Stop immediately after giving the JSON
            }
        }, timeout=60) # 60 seconds timeout - is a bit high but LLMs can be slow sometimes
        
        r.raise_for_status()
        response_data = r.json()
        model_output = json.loads(response_data.get('response', '{}'))
        return model_output.get('is_promotional', False), model_output.get('reason', 'N/A')
    
    except requests.exceptions.Timeout:
        return False, "LLM Timeout (Still thinking...)"
    
    except Exception as e:
        return False, f"LLM Error: {str(e)}"

def run_tuning_session(storage_dir: str = None):
    storage_dir = storage_dir or STORAGE_DIR

    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Timestamped, human-sortable filename
    ts = time.strftime('%Y%m%d-%H%M%S')
    results_path = os.path.join(RESULTS_DIR, f'tuning_{ts}.csv')

    files = get_latest_emails(storage_dir, count=50)  # Start with 50 for speed
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