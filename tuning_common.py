import os
import email
from email import policy

# Global paths shared by local and cloud tuning
STORAGE_DIR = os.environ.get(
    "EMAIL_STORAGE_DIR", "/srv/storage/docker/email_data/raw_emails"
)
RESULTS_DIR = os.environ.get("TUNING_RESULTS_DIR", "./tuning_results")


def get_latest_emails(directory, count=50):
    """Returns the filenames of the newest emails based on sequence ID."""
    files = [f for f in os.listdir(directory) if f.endswith(".eml")]
    files.sort(key=lambda x: int(x.split(".")[0]), reverse=True)
    return files[:count]


def parse_eml(filepath):
    """Extracts basic info from an eml file for the LLM, including Message-ID and Date."""
    try:
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        sender = msg.get("from", "(Unknown)")
        subject = msg.get("subject", "(No Subject)")
        message_id = msg.get("Message-ID", "(No Message-ID)")
        email_date = msg.get("Date", "(no date)")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="ignore")

        snippet = body.strip().replace("\n", " ")[:500]
        return sender, subject, snippet, message_id, email_date
    except Exception as e:
        return "Error", "Error", str(e), "(Error)", "(no date)"
