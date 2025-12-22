import os
import email
from email import policy
import requests
import json

OLLAMA_API_URL = 'http://127.0.0.1:11434/api/generate'
OLLAMA_MODEL = 'mistral:7b-instruct-q5_K_M'

def get_latest_emails(directory, count=50):
    """Returns the filenames of the newest emails based on sequence ID."""
    files = [f for f in os.listdir(directory) if f.endswith('.eml')]
    # Sort numerically descending (Highest SeqID = Newest)
    files.sort(key=lambda x: int(x.split('.')[0]), reverse=True)
    return files[:count]

def parse_eml(filepath):
    """Extracts basic info from an eml file for the LLM."""
    try:
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        
        sender = msg.get('from', '(Unknown)')
        subject = msg.get('subject', '(No Subject)')
        
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
        return sender, subject, snippet
    except Exception as e:
        return "Error", "Error", str(e)

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
    - A personal/direct human-to-human conversation
    - A formal receipt or order confirmation
    - Critical account security or legal alerts
    - Important updates from services I actively use
    - medical related emails from my doctor, hospital, or health insurance provider
    - if its from family, friends, or colleagues
    - if its from myself (my own email address or variants of it. keithpyle@gmail okeefo@gmail.com, xxkeefxx@gmail.com and okeefo@live.co.uk)
    - it it from HMRC regarding tax, returns or self assessment
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
            "format": "json"
        }, timeout=60)
        
        r.raise_for_status()
        response_data = r.json()
        model_output = json.loads(response_data.get('response', '{}'))
        return model_output.get('is_promotional', False), model_output.get('reason', 'N/A')
    
    except requests.exceptions.Timeout:
        return False, "LLM Timeout (Still thinking...)"
    
    except Exception as e:
        return False, f"LLM Error: {str(e)}"

def run_tuning_session(storage_dir):
    files = get_latest_emails(storage_dir, count=30) # Start with 30 for speed
    print(f"\n--- Tuning Session: Reviewing {len(files)} Newest Emails ---")
    
    for filename in files:
        path = os.path.join(storage_dir, filename)
        sender, subject, snippet = parse_eml(path)
        is_promo, reason = classify_email(sender, subject, snippet)
        
        status = "[DELETE]" if is_promo else "[ KEEP ]"
        print(f"{status} | {subject[:50]:<50} | {reason}")