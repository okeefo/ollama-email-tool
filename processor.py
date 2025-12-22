import os
import sys
import csv
import shutil
from typing import List
import email
from email import policy


# Defaults align with tuner.py and storage layout
STORAGE_DIR = os.environ.get('EMAIL_STORAGE_DIR', '/srv/storage/docker/email_data/raw_emails')
RESULTS_DIR = os.environ.get('TUNING_RESULTS_DIR', './tuning_results')
STAGING_DIR = os.environ.get('STAGING_TO_DELETE_DIR', '/srv/storage/docker/email_data/staging/to_delete')


def _list_tuning_csvs(results_dir: str) -> List[str]:
    if not os.path.isdir(results_dir):
        return []
    files = [
        os.path.join(results_dir, f)
        for f in os.listdir(results_dir)
        if f.startswith('tuning_') and f.endswith('.csv')
    ]
    # Sort by filename descending (tuning_YYYYMMDD-HHMMSS.csv → lexicographic = chronological)
    files.sort(reverse=True)
    return files


def _read_email_date(path: str) -> str:
    try:
        with open(path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        return msg.get('Date', '(no date)')
    except Exception:
        return '(no date)'


def _trim(text: str, max_len: int = 60) -> str:
    s = (text or '').replace('\n', ' ').strip()
    return s if len(s) <= max_len else s[: max_len - 1] + '…'


def _process_csv(csv_path: str, raw_dir: str, staging_dir: str) -> dict:
    moved = 0
    already = 0
    missing = 0
    errors = 0

    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get('status') or '').strip()
            if status != '[DELETE]':
                continue

            seq_id = str(row.get('seq_id') or '').strip()
            subject = row.get('subject') or ''
            reason = row.get('reason') or ''

            # Determine file names/paths
            filename = f"{seq_id}.eml" if seq_id.isdigit() else None
            src = os.path.join(raw_dir, filename) if filename else None
            dst = os.path.join(staging_dir, filename) if filename else None

            # Resolve status line fields
            date_str = '(missing)'

            try:
                if not filename:
                    missing += 1
                    print(f"MISSING | id={seq_id:<6} | date={date_str:<25} | subj={_trim(subject)} | reason={_trim(reason, 80)}")
                    continue

                # If already staged
                if os.path.exists(dst):
                    date_str = _read_email_date(dst)
                    already += 1
                    print(f"SKIP   | id={seq_id:<6} | date={date_str:<25} | subj={_trim(subject)} | reason={_trim(reason, 80)}")
                    continue

                # If in raw, move it
                if os.path.exists(src):
                    # Read date before moving for consistent reporting
                    date_str = _read_email_date(src)
                    os.makedirs(staging_dir, exist_ok=True)
                    shutil.move(src, dst)
                    moved += 1
                    print(f"MOVED  | id={seq_id:<6} | date={date_str:<25} | subj={_trim(subject)} | reason={_trim(reason, 80)}")
                else:
                    missing += 1
                    print(f"MISSING | id={seq_id:<6} | date={date_str:<25} | subj={_trim(subject)} | reason={_trim(reason, 80)}")
            except Exception as e:
                errors += 1
                print(f"ERROR  | id={seq_id:<6} | {e}")

    return {"moved": moved, "already": already, "missing": missing, "errors": errors}


def run_processor(storage_dir: str = None, results_dir: str = None, staging_dir: str = None):
    raw_dir = storage_dir or STORAGE_DIR
    res_dir = results_dir or RESULTS_DIR
    stage_dir = staging_dir or STAGING_DIR

    csvs = _list_tuning_csvs(res_dir)
    if not csvs:
        print(f"No tuning CSVs found in: {res_dir}")
        return

    print("\n--- Tuning Results Available ---")
    for i, p in enumerate(csvs, start=1):
        print(f"{i:2d}. {os.path.basename(p)}")

    print("\nSelect CSVs to process:")
    print(" - Enter comma-separated numbers (e.g. 1,3,4)")
    print(" - Enter 'L' for latest only")
    print(" - Enter 'A' for all")
    print(" - Enter 'E' to cancel")

    choice = input("Your choice: ").strip().upper()
    if choice == 'E':
        print("Cancelled.")
        return

    if choice == 'L':
        selected = [csvs[0]]
    elif choice == 'A':
        selected = csvs
    else:
        try:
            idxs = [int(x) for x in choice.split(',') if x.strip().isdigit()]
            selected = [csvs[i - 1] for i in idxs if 1 <= i <= len(csvs)]
        except Exception:
            print("Invalid selection.")
            return

    if not selected:
        print("No files selected.")
        return

    print(f"\nProcessing {len(selected)} CSV file(s)…")
    grand = {"moved": 0, "already": 0, "missing": 0, "errors": 0}

    for path in selected:
        print("\n" + "-" * 80)
        print(f"Processing: {os.path.basename(path)}")
        res = _process_csv(path, raw_dir, stage_dir)
        for k in grand:
            grand[k] += res.get(k, 0)

    print("\n" + "=" * 80)
    print("Summary:")
    print(f" - Moved:   {grand['moved']}")
    print(f" - Skipped: {grand['already']} (already staged)")
    print(f" - Missing: {grand['missing']}")
    if grand['errors']:
        print(f" - Errors:  {grand['errors']}")
    print("=" * 80)


if __name__ == '__main__':
    # Optional CLI usage: python processor.py [RAW_DIR] [RESULTS_DIR] [STAGING_DIR]
    raw = sys.argv[1] if len(sys.argv) > 1 else None
    res = sys.argv[2] if len(sys.argv) > 2 else None
    stage = sys.argv[3] if len(sys.argv) > 3 else None
    run_processor(raw, res, stage)
