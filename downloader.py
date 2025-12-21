import imaplib
import mailbox
from datetime import date, timedelta

def fetch_all_older_than_90_days(user, password, full_file_path):
    print(f"\nConnecting to Gmail...")
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com')
        M.login(user, password)
        M.select('INBOX')

        three_months_ago = (date.today() - timedelta(days=90)).strftime("%d-%b-%Y")
        search_query = f'(BEFORE "{three_months_ago}")'
        
        status, data = M.search(None, search_query)
        email_ids = data[0].split()
        
        total = len(email_ids)
        if total == 0:
            print("No emails found matching the criteria.")
            return

        print(f"Found {total} emails. Starting download to {full_file_path}...")

        # Open an mbox file for writing
        mbox = mailbox.mbox(full_file_path)
        mbox.lock()

        try:
            for i, num in enumerate(email_ids):
                status, data = M.fetch(num, '(RFC822)')
                raw_email = data[0][1]
                
                # Add to mbox
                mbox.add(raw_email)
                
                if (i + 1) % 100 == 0:
                    print(f"Progress: {i + 1}/{total} downloaded...")
            
            mbox.flush()
        finally:
            mbox.unlock()
            mbox.close()

        M.logout()
        print(f"\nFinished! {total} emails saved to {full_file_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
