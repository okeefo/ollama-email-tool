import imaplib
import os
import email
import json
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

# --- CONFIG ---
# Load environment variables from the .env file
load_dotenv()

GMAIL_USER = os.getenv('GMAIL_USER')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
IMAP_SERVER = 'imap.gmail.com'
OLLAMA_API_URL = 'http://127.0.0.1:11434/api/generate'
OLLAMA_MODEL = 'mistral:7b-instruct-q5_K_M'
OUTPUT_FILE = '/srv/storage/docker/email_data/deletions.csv'

# --- 1. LLM Classification Function ---
def classify_with_ollama(sender, subject, body_snippet):
    """Sends email data to the local LLM and returns the classification."""
    
    # The prompt is designed for Mistral to output structured JSON
    prompt = f"""
    You are an expert email classifier. Analyze the following email to determine if it is a low-priority promotional, marketing, or newsletter email (excluding personal conversations, receipts, order confirmations, and essential system updates). The email must be flagged true ONLY if it is promotional or a marketing newsletter.

    EMAIL DATA:
    Sender: {sender}
    Subject: {subject}
    Body Snippet (Max 500 chars): {body_snippet}

    OUTPUT ONLY A VALID, SINGLE JSON OBJECT: {{"is_promotional": true/false, "reason": "brief classification reason"}}
    """

    try:
        # We send the request to your local Ollama API
        response = requests.post(OLLAMA_API_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json" # Crucial for forcing structured output
        })
        
        # Check for successful API response
        response.raise_for_status() 
        
        # Ollama's response is a JSON string inside a 'response' field
        response_data = response.json()
        
        # Attempt to parse the actual JSON output from the model
        model_output = json.loads(response_data.get('response', '{}'))
        
        return model_output.get('is_promotional', False)

    except requests.exceptions.RequestException as e:
        print(f"Ollama API Error: {e}. Is your Ollama container running?")
        return False
    except json.JSONDecodeError:
        print("LLM returned malformed JSON. Skipping.")
        return False

# --- 2. Email Fetching and Processing ---
def fetch_and_process_emails():
    M = imaplib.IMAP4_SSL(IMAP_SERVER)
    M.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    M.select('INBOX') 

    # We are still using the same search query (emails since yesterday)
    yesterday = (date.today() - timedelta(days=1)).strftime("%d-%b-%Y")
    search_query = f'(SINCE "{yesterday}" NOT X-GM-LABELS "Social" NOT X-GM-LABELS "Forums" NOT X-GM-LABELS "Receipts")'
    
    # Search for email UIDs (Unique Identifiers)
    status, data = M.uid('search', None, search_query)
    uids = data[0].split()
    
    if not uids:
        print("No emails to process.")
        return

    print(f"Found {len(uids)} emails. Starting LLM classification...")
    
    deletion_list = []
    
    # Fetch the entire message content (RFC822)
    for i, uid_bytes in enumerate(uids):
        uid = uid_bytes.decode()
        
        # Fetch the FULL message body (RFC822)
        status, data = M.uid('fetch', uid, '(RFC822)')
        if status != 'OK' or not data or not data[0]:
            print(f"Failed to fetch content for UID {uid}. Skipping.")
            continue

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Basic text extraction from the email object
        body_snippet = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = part.get_content_disposition()

                # Find the plaintext body
                if ctype == 'text/plain' and cdispo is None:
                    try:
                        body_snippet = part.get_payload(decode=True).decode()
                    except:
                        pass # Handle decoding errors
                    break
        else:
             # Handle non-multipart emails (plain text or simple HTML)
            if msg.get_content_type() == 'text/plain':
                 body_snippet = msg.get_payload(decode=True).decode()
        
        # Clean up the body snippet
        body_snippet = body_snippet.strip().replace('\n', ' ')[:500] 

        sender = msg['from'] if msg['from'] else '(Unknown)'
        subject = msg['subject'] if msg['subject'] else '(No Subject)'
        
        # --- LLM CALL ---
        is_promo = classify_with_ollama(sender, subject, body_snippet)
        
        if is_promo:
            deletion_list.append({
                'uid': uid,
                'message_id': msg['message-id'],
                'subject': subject,
                'sender': sender
            })
            print(f"[{i+1}/{len(uids)}] Classified as PROMOTIONAL: {subject[:50]}...")
        else:
            print(f"[{i+1}/{len(uids)}] Classified as KEEP: {subject[:50]}...")
            
    M.logout()
    print("IMAP session closed.")
    return deletion_list

# --- 3. Save Output ---
if __name__ == "__main__":
    if not os.path.exists(os.path.dirname(OUTPUT_FILE)):
        os.makedirs(os.path.dirname(OUTPUT_FILE))
        print(f"Created output directory: {os.path.dirname(OUTPUT_FILE)}")
    
    
    # Ensure the required libraries are installed (though already done in venv)
    # The script should be run in the active virtual environment
    try:
        emails_to_delete = fetch_and_process_emails()

        if emails_to_delete:
            df = pd.DataFrame(emails_to_delete)
            df.to_csv(OUTPUT_FILE, index=False)
            print(f"\n--- SUCCESS! ---")
            print(f"Total promotional emails flagged: {len(emails_to_delete)}")
            print(f"List saved to: {OUTPUT_FILE}")
        else:
            print("No promotional emails flagged for deletion.")

    except Exception as e:
        print(f"A final error occurred: {e}")
