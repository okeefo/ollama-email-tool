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
STAGING_KEEP_DIR = os.environ.get('STAGING_KEEP_DIR', '/srv/storage/docker/email_data/staging/to_keep')


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


def _process_csv(
    csv_path: str,
    raw_dir: str,
    delete_dir: str,
    keep_dir: str,
    mode: str = 'move',
    apply_keep: bool = True,
    apply_delete: bool = True,
    dry_run: bool = False,
) -> dict:
    stats = {
        "moved_delete": 0,
        "moved_keep": 0,
        "reverted_delete": 0,
        "reverted_keep": 0,
        "already": 0,
        "missing": 0,
        "errors": 0,
    }

    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get('status') or '').strip()  # '[DELETE]' or '[ KEEP ]' or others
            seq_id = str(row.get('seq_id') or '').strip()
            subject = (row.get('subject') or '')

            # Only act on requested statuses
            if status == '[DELETE]' and not apply_delete:
                continue
            if status == '[ KEEP ]' and not apply_keep:
                continue
            if status not in ('[DELETE]', '[ KEEP ]'):
                # Unknown or summary rows: skip silently
                continue

            if not seq_id.isdigit():
                stats["missing"] += 1
                continue

            filename = f"{seq_id}.eml"

            try:
                if mode == 'move':
                    src = os.path.join(raw_dir, filename)
                    if status == '[DELETE]':
                        dst = os.path.join(delete_dir, filename)
                        label = 'DELETE'
                    else:
                        dst = os.path.join(keep_dir, filename)
                        label = 'KEEP'

                    # Already in either staging?
                    if os.path.exists(os.path.join(delete_dir, filename)) or os.path.exists(os.path.join(keep_dir, filename)):
                        stats["already"] += 1
                        continue

                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        if dry_run:
                            print(f"DRY-RUN MOVE {label} | id={seq_id:<6} | {_trim(subject, 50)}")
                        else:
                            shutil.move(src, dst)
                            print(f"MOVED     {label} | id={seq_id:<6} | {_trim(subject, 50)}")
                        if status == '[DELETE]':
                            stats["moved_delete"] += 1
                        else:
                            stats["moved_keep"] += 1
                    else:
                        stats["missing"] += 1

                elif mode == 'revert':
                    if status == '[DELETE]':
                        src = os.path.join(delete_dir, filename)
                        label = 'DELETE'
                    else:
                        src = os.path.join(keep_dir, filename)
                        label = 'KEEP'
                    dst = os.path.join(raw_dir, filename)

                    # Already back in raw?
                    if os.path.exists(dst):
                        stats["already"] += 1
                        continue

                    if os.path.exists(src):
                        os.makedirs(raw_dir, exist_ok=True)
                        if dry_run:
                            print(f"DRY-RUN REVERT {label} | id={seq_id:<6} | {_trim(subject, 50)}")
                        else:
                            shutil.move(src, dst)
                            print(f"REVERTED  {label} | id={seq_id:<6} | {_trim(subject, 50)}")
                        if status == '[DELETE]':
                            stats["reverted_delete"] += 1
                        else:
                            stats["reverted_keep"] += 1
                    else:
                        stats["missing"] += 1
                else:
                    # Unknown mode
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"ERROR | id={seq_id} | {e}")

    return stats


def run_processor(storage_dir: str = None, results_dir: str = None, staging_dir: str = None):
    raw_dir = storage_dir or STORAGE_DIR
    res_dir = results_dir or RESULTS_DIR
    stage_del_dir = staging_dir or STAGING_DIR
    stage_keep_dir = STAGING_KEEP_DIR

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

    # Choose operation mode
    print("\nOperation modes:")
    print(" M1 - Move KEEP only")
    print(" M2 - Move DELETE only")
    print(" M3 - Move KEEP and DELETE (default)")
    print(" R1 - Revert KEEP only")
    print(" R2 - Revert DELETE only")
    print(" R3 - Revert KEEP and DELETE")
    op_choice = input("Select mode [M3]: ").strip().upper() or 'M3'

    mode = 'move'
    apply_keep = True
    apply_delete = True
    if op_choice == 'M1':
        mode = 'move'; apply_keep = True; apply_delete = False
    elif op_choice == 'M2':
        mode = 'move'; apply_keep = False; apply_delete = True
    elif op_choice == 'M3':
        mode = 'move'; apply_keep = True; apply_delete = True
    elif op_choice == 'R1':
        mode = 'revert'; apply_keep = True; apply_delete = False
    elif op_choice == 'R2':
        mode = 'revert'; apply_keep = False; apply_delete = True
    elif op_choice == 'R3':
        mode = 'revert'; apply_keep = True; apply_delete = True
    else:
        print("Unknown selection; defaulting to Move KEEP and DELETE.")
        mode = 'move'; apply_keep = True; apply_delete = True

    dry_raw = input("Dry run? (y/N): ").strip().lower()
    dry_run = dry_raw == 'y'

    print(f"\nProcessing {len(selected)} CSV file(s)… ({'DRY-RUN' if dry_run else 'REAL'})")
    grand = {"moved_delete": 0, "moved_keep": 0, "reverted_delete": 0, "reverted_keep": 0, "already": 0, "missing": 0, "errors": 0}

    for path in selected:
        print("\n" + "-" * 80)
        print(f"Processing: {os.path.basename(path)}")
        res = _process_csv(
            path,
            raw_dir,
            stage_del_dir,
            stage_keep_dir,
            mode=mode,
            apply_keep=apply_keep,
            apply_delete=apply_delete,
            dry_run=dry_run,
        )
        for k in grand:
            grand[k] += res.get(k, 0)

    print("\n" + "=" * 80)
    print("Summary:")
    print(f" - Moved to delete:   {grand['moved_delete']}")
    print(f" - Moved to keep:     {grand['moved_keep']}")
    print(f" - Reverted delete:   {grand['reverted_delete']}")
    print(f" - Reverted keep:     {grand['reverted_keep']}")
    print(f" - Skipped (already): {grand['already']}")
    print(f" - Missing:           {grand['missing']}")
    if grand['errors']:
        print(f" - Errors:            {grand['errors']}")
    print("=" * 80)


if __name__ == '__main__':
    # Optional CLI usage: python processor.py [RAW_DIR] [RESULTS_DIR] [STAGING_DIR]
    raw = sys.argv[1] if len(sys.argv) > 1 else None
    res = sys.argv[2] if len(sys.argv) > 2 else None
    stage = sys.argv[3] if len(sys.argv) > 3 else None
    run_processor(raw, res, stage)
