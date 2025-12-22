import os
from typing import List

# Defaults align with tuner.py
RESULTS_DIR = os.environ.get('TUNING_RESULTS_DIR', './tuning_results')


def _list_tuning_csvs(results_dir: str) -> List[str]:
    if not os.path.isdir(results_dir):
        return []
    files = [
        os.path.join(results_dir, f)
        for f in os.listdir(results_dir)
        if f.startswith('tuning_') and f.endswith('.csv')
    ]
    files.sort(reverse=True)
    return files


def _human_size(num: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"


def _parse_indices(s: str, max_n: int) -> List[int]:
    out = []
    parts = [x.strip() for x in s.split(',') if x.strip()]
    for part in parts:
        if '-' in part:
            a, b = part.split('-', 1)
            if a.isdigit() and b.isdigit():
                start = int(a)
                end = int(b)
                if start <= end:
                    for k in range(start, end + 1):
                        if 1 <= k <= max_n:
                            out.append(k)
        elif part.isdigit():
            k = int(part)
            if 1 <= k <= max_n:
                out.append(k)
    # dedupe preserving order
    seen = set()
    uniq = []
    for k in out:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def manage_tuning_runs(results_dir: str = None):
    """Interactive manager for previous tuning runs: list, delete, open in nano."""
    res_dir = results_dir or RESULTS_DIR

    def list_and_print() -> List[str]:
        csvs = _list_tuning_csvs(res_dir)
        if not csvs:
            print(f"No tuning CSVs found in: {res_dir}")
            return []
        print("\n--- Tuning Runs ---")
        for i, p in enumerate(csvs, start=1):
            try:
                st = os.stat(p)
                size = _human_size(st.st_size)
                mtime = st.st_mtime
                from time import strftime, localtime
                when = strftime('%Y-%m-%d %H:%M:%S', localtime(mtime))
            except Exception:
                size = '?'
                when = '?'
            print(f"{i:2d}. {os.path.basename(p)}  [{size}, {when}]")
        return csvs

    while True:
        csvs = list_and_print()
        if not csvs:
            return

        print("\nOptions: [O]pen  [D]elete  [DA] Delete All  [R]efresh  [E]xit")
        choice = input("Select: ").strip().upper()

        if choice == 'E':
            return
        elif choice == 'R':
            continue
        elif choice == 'DA':
            confirm = input("Delete ALL tuning CSVs? Type 'DELETE' to confirm: ").strip()
            if confirm == 'DELETE':
                deleted = 0
                for p in csvs:
                    try:
                        os.remove(p)
                        deleted += 1
                    except Exception as e:
                        print(f"Failed to delete {os.path.basename(p)}: {e}")
                print(f"Deleted {deleted} file(s).")
            else:
                print("Cancelled.")
        elif choice == 'D':
            sel = input("Enter number(s) or ranges (e.g. 1,3-5): ").strip()
            idxs = _parse_indices(sel, len(csvs))
            if not idxs:
                print("No valid selection.")
                continue
            print("You selected:")
            for i in idxs:
                print(f" - {os.path.basename(csvs[i-1])}")
            confirm = input("Type 'DELETE' to confirm: ").strip()
            if confirm != 'DELETE':
                print("Cancelled.")
                continue
            deleted = 0
            for i in idxs:
                p = csvs[i-1]
                try:
                    os.remove(p)
                    deleted += 1
                except Exception as e:
                    print(f"Failed to delete {os.path.basename(p)}: {e}")
            print(f"Deleted {deleted} file(s).")
        elif choice == 'O':
            sel = input("Enter number to open: ").strip()
            if not sel.isdigit():
                print("Invalid selection.")
                continue
            i = int(sel)
            if not (1 <= i <= len(csvs)):
                print("Out of range.")
                continue
            p = csvs[i-1]
            editor = os.environ.get('EDITOR', 'nano')
            os.system(f"{editor} '{p}'")
        else:
            print("Unknown option.")
