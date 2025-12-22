import os
from datetime import date
from dotenv import load_dotenv
import utils
import downloader
import tuner
import processor
import tuning_runs_manager

load_dotenv()

def main_menu():
    while True:
        print("\n" + "="*30)
        print(" GMAIL AI ORGANIZER (Control) ")
        print("="*30)
        print("1. Fetch all emails (> 3 months old)")
        print("2. Run Tuning/Review Session (default 50)")
        print("3. Process Tuning Results (move to staging)")
        print("4. Manage Tuning Runs (list/open/delete)")
        print("E. Exit")
        
        choice = input("\nSelect Option: ").strip().upper()

        if choice == '1':
            default_dir = "/srv/storage/docker/email_data"
            target_dir = utils.get_target_directory(default_dir)
            
            if target_dir:
                default_file = f"gmail_archive_{date.today().isoformat()}.mbox"
                full_path = utils.get_target_filename(target_dir, default_file)
                
                if full_path:
                    downloader.fetch_all_older_than_90_days(
                        os.getenv('GMAIL_USER'),
                        os.getenv('GMAIL_APP_PASSWORD'),
                        full_path
                    )

        elif choice == '2':
            storage_dir = "/srv/storage/docker/email_data/raw_emails"
            # Prompt for how many emails to review (default 50)
            raw = input("How many emails to review? (Enter for 50): ").strip()
            try:
                n = int(raw) if raw else 50
                if n <= 0:
                    raise ValueError()
            except Exception:
                n = 50
            tuner.run_tuning_session(storage_dir, count=n)
        
        elif choice == '3':
            storage_dir = "/srv/storage/docker/email_data/raw_emails"
            # results_dir and staging_dir default via env; pass only storage_dir here
            processor.run_processor(storage_dir=storage_dir)
        
        elif choice == '4':
            # Manage previous tuning runs: list/delete/open
            tuning_runs_manager.manage_tuning_runs()
            
        elif choice == 'E':
            print("Goodbye Keith!")
            break
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main_menu()
