import os

def get_target_directory(default_dir):
    print(f"\n[Storage Setup]")
    print(f"Current directory: {default_dir}")
    choice = input("Accept this directory? (Enter for Yes, or type new path): ").strip()
    
    target = choice if choice else default_dir
    
    if not os.path.exists(target):
        create = input(f"Path '{target}' does not exist. Create it? (y/n): ").lower()
        if create == 'y':
            os.makedirs(target, exist_ok=True)
        else:
            return None
    return target

def get_target_filename(directory, default_name):
    while True:
        print(f"\nSuggested filename: {default_name}")
        choice = input("Accept filename? (Enter for Yes, or type new name): ").strip()
        
        filename = choice if choice else default_name
        # Ensure it ends in .eml or .mbox depending on what we decide
        if not filename.endswith('.mbox'):
             filename += ".mbox"
             
        full_path = os.path.join(directory, filename)
        
        if os.path.exists(full_path):
            overwrite = input(f"!!! File '{filename}' already exists. Overwrite? (y/n): ").lower()
            if overwrite == 'y':
                return full_path
            else:
                print("Let's try a different name.")
                continue
        return full_path
