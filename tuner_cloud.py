import os
import time
import csv
import json

from tuning_common import STORAGE_DIR, RESULTS_DIR, get_latest_emails, parse_eml

try:
    from google import genai  # modern 2026 SDK
    from google.genai import types
except Exception:
    genai = None
    types = None


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or genai is None:
        raise RuntimeError("GEMINI_API_KEY not set or google-genai not installed.")
    return genai.Client(api_key=api_key)


def process_cloud_batch(email_batch, model: str = None):
    """Modern google-genai Client-based batch processing."""
    if genai is None or types is None:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    # Default model: prefer env override, else gemini-3-flash-preview per suggestion
    model_name = model or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    client = _get_client()

    prompt = (
        "AUDIT TASK: Review the following email list.\n"
        "Identify which are PROMOTIONAL (Junk/Automated) vs IMPORTANT (Personal/Financial/Medical).\n\n"
        "CRITICAL: Be aggressive with LinkedIn and Social Media pings. Even if they say "
        "'Personal message', if they originate from a social platform, mark as is_promotional: true.\n\n"
        "Return ONLY a JSON array of objects:\n"
        '[{"seq_id": "123", "is_promotional": true, "reason": "string"}]\n'
    )

    email_texts = "\n".join(
        [
            f"ID: {e['seq_id']} | From: {e['sender']} | Sub: {e['subject']} | Snippet: {e['snippet']}"
            for e in email_batch
        ]
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt + "\n\nEMAILS TO AUDIT:\n" + email_texts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = json.loads(getattr(response, "text", "") or "[]")
        # Ensure standardized list format
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            out.append(
                {
                    "seq_id": str(item.get("seq_id")),
                    "is_promotional": bool(item.get("is_promotional")),
                    "reason": item.get("reason") or "N/A",
                }
            )
        return out
    except Exception as e:
        print(f"Cloud Logic Error: {e}")
        return []


def run_cloud_tuning_session(
    storage_dir: str = None, count: int = 500, batch_size: int = 50, model: str = None
):
    storage_dir = storage_dir or STORAGE_DIR
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Early check for API key existence
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) not set. Add to your .env and reload."
        )
        return

    ts = time.strftime("%Y%m%d-%H%M%S")
    results_path = os.path.join(RESULTS_DIR, f"tuning_{ts}.csv")

    files = get_latest_emails(storage_dir, count=count)
    print(
        f"\n--- Tuning Session (Cloud): Reviewing {len(files)} Newest Emails (batch={batch_size}) ---"
    )

    total_start = time.time()
    ai_total = 0.0
    ai_count = 0

    # Pre-parse all needed email info once
    parsed = {}
    for filename in files:
        path = os.path.join(storage_dir, filename)
        try:
            seq_id = int(os.path.splitext(filename)[0])
        except Exception:
            seq_id = -1
        start_parse = time.time()
        sender, subject, snippet, message_id = parse_eml(path)
        parse_sec = time.time() - start_parse
        parsed[str(seq_id)] = {
            "seq_id": str(seq_id),
            "sender": sender,
            "subject": subject,
            "snippet": snippet,
            "message_id": message_id,
            "parse_sec": parse_sec,
        }

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

        seq_ids_ordered = [str(int(os.path.splitext(f)[0])) for f in files]

        for i in range(0, len(seq_ids_ordered), batch_size):
            chunk_ids = seq_ids_ordered[i : i + batch_size]
            email_batch = [
                {
                    "seq_id": pid,
                    "sender": parsed[pid]["sender"],
                    "subject": parsed[pid]["subject"],
                    "snippet": parsed[pid]["snippet"],
                }
                for pid in chunk_ids
            ]

            print(
                f"Sending batch {i // batch_size + 1} to Gemini… ({len(email_batch)} emails)"
            )
            start_ai = time.time()
            results = process_cloud_batch(email_batch, model=model)
            ai_duration = time.time() - start_ai
            per_email_ai_sec = ai_duration / max(1, len(email_batch))

            res_map = {str(r.get("seq_id")): r for r in results}

            for pid in chunk_ids:
                base = parsed[pid]
                r = res_map.get(
                    pid, {"is_promotional": False, "reason": "No decision returned"}
                )
                is_promo = bool(r.get("is_promotional", False))
                reason = r.get("reason") or "N/A"
                status = "[DELETE]" if is_promo else "[ KEEP ]"

                ai_total += per_email_ai_sec
                ai_count += 1
                ai_avg = ai_total / ai_count if ai_count else 0.0

                print(
                    f"{status} | {base['subject'][:40]:<40} | {per_email_ai_sec:4.1f}s (avg {ai_avg:4.1f}s) | {reason}"
                )

                writer.writerow(
                    [
                        base["seq_id"],
                        base["message_id"],
                        status,
                        base["subject"],
                        f"{base['parse_sec']:.3f}",
                        f"{per_email_ai_sec:.3f}",
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

    total_duration = time.time() - total_start
    print("\n" + "=" * 80)
    print(
        f"Cloud Session Complete: {len(files)} emails in {total_duration:.1f}s "
        f"(Avg: {total_duration/max(1,len(files)):.1f}s per email)"
    )
    print(f"Saved results to: {results_path}")
    print("=" * 80)
