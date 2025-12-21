import os
from datetime import date
from dotenv import load_dotenv
import utils
import downloader

load_dotenv()

def main_menu():
    while True:
        print("\n" + "="*30)
        print(" GMAIL AI ORGANIZER (Control) ")
        print("="*30)
        print("1. Fetch all emails (> 3 months old)")
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

        elif choice == 'E':
            print("Goodbye Keith!")
            break
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main_menu()
