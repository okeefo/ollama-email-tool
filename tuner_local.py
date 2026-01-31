import os
import time
import csv
import requests
import json

from tuning_common import STORAGE_DIR, RESULTS_DIR, get_latest_emails, parse_eml

OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "email-triage")
REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))
OPTIONS = {
    "temperature": float(os.environ.get("OLLAMA_TEMPERATURE", "0.0")),
    "num_thread": int(os.environ.get("OLLAMA_NUM_THREAD", "8")),
    "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "128")),
    "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "1024")),
}


def _parse_model_json(response_text: str):
    if not response_text:
        return None
    s = response_text.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    str_ch = ""
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == str_ch:
                in_str = False
        else:
            if c == '"' or c == "'":
                in_str = True
                str_ch = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    segment = s[start : i + 1]
                    try:
                        return json.loads(segment)
                    except Exception:
                        return None
    return None


def _retry_strict_json(prompt: str):
    strict_prompt = (
        prompt
        + "\n\nReturn ONLY a single JSON object with keys: is_promotional (boolean), reason (string)."
    )
    try:
        r = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": strict_prompt,
                "stream": False,
                "format": "json",
                "options": {
                    **OPTIONS,
                    "num_predict": min(OPTIONS.get("num_predict", 128), 64),
                },
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        response_data = r.json()
        parsed = _parse_model_json(response_data.get("response", ""))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _heuristic_classify(sender: str, subject: str, snippet: str):
    text = " ".join([sender or "", subject or "", snippet or ""]).lower()
    promo_keywords = [
        "unsubscribe",
        "sale",
        "discount",
        "newsletter",
        "offer",
        "deal",
        "promotion",
        "shop",
        "limited time",
        "confirm",
        "pick of the week",
        "pricing",
        "property",
        "free",
        "save",
        "coupon",
        "act now",
    ]
    sender_flags = ["noreply", "no-reply", "mailer", "marketing", "news"]
    is_promo = any(k in text for k in promo_keywords) or any(
        s in (sender or "").lower() for s in sender_flags
    )
    if is_promo:
        return True, "Heuristic promotional keywords/sender"
    return False, "Heuristic non-promotional"


def classify_email(sender, subject, snippet, email_date=None):
    """Call local Ollama model using the custom 'email-triage' modelfile with minimal prompt."""
    prompt = (
        f"Date: {email_date or '(no date)'}\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Body Snippet: {snippet}"
    )
    try:
        r = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": OPTIONS,
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        response_data = r.json()
        parsed = _parse_model_json(response_data.get("response", ""))
        if isinstance(parsed, dict):
            return parsed.get("is_promotional", False), parsed.get("reason", "N/A")
        retry_parsed = _retry_strict_json(prompt)
        if isinstance(retry_parsed, dict):
            return retry_parsed.get("is_promotional", False), retry_parsed.get(
                "reason", "N/A"
            )
        h_is_promo, h_reason = _heuristic_classify(sender, subject, snippet)
        return h_is_promo, h_reason
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
    print(f"Using local model: {OLLAMA_MODEL}")
    print(
        f"Endpoint: {OLLAMA_API_URL} | KeepAlive={os.environ.get('OLLAMA_KEEP_ALIVE', '(unset)')}"
    )
    print(
        f"Options: temperature={OPTIONS['temperature']}, num_thread={OPTIONS['num_thread']}, "
        f"num_predict={OPTIONS['num_predict']}, num_ctx={OPTIONS['num_ctx']}"
    )
    # Warm up the model once to avoid first-request stall
    try:
        warm_start = time.time()
        requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": "Warm-up",
                "stream": False,
                "format": "json",
                "options": {**OPTIONS, "num_predict": 16},
            },
            timeout=min(REQUEST_TIMEOUT, 120),
        )
        print(f"Warm-up complete in {time.time() - warm_start:.1f}s")
    except Exception as e:
        print(f"Warm-up skipped ({e})")

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
            sender, subject, snippet, message_id, email_date = parse_eml(path)
            parse_duration = time.time() - start_parse

            start_ai = time.time()
            is_promo, reason = classify_email(sender, subject, snippet, email_date)
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
