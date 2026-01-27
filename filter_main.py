import os
import time
import sys

# Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from log_cleaner import LogCleaner
from database_manager import DatabaseManager
from extract_crash import extract_crash


LOG_FILE_PATH = "/home/amlogic/RAG/clean_log/store_log_data/IPTV-27435/failed/IPTV-27435_BJ-IPTV-26084-h264-花屏.log"
def clean_log():
    # Target log file path
    
    log_file_path = LOG_FILE_PATH
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}")
        return
    log_current_dir = os.path.dirname(os.path.abspath(log_file_path))
    # 0. Extract crashes from log file
    extract_crash(log_file_path)
    start_time = time.time()

    # 1. Clean the log (Use existing logic to get cleaned content for comparison)
    cleaner = LogCleaner(log_file_path)
    clean_file_path, all_log_content = cleaner.clean_log()

    if not clean_file_path or not os.path.exists(clean_file_path):
        print("Log cleaning failed.")
        return

    # 2. Connect to Database to get existing cleaned logs
    # db_path = os.path.join(current_dir, "log_data.db")
    # db_manager = DatabaseManager(db_path)
    
    # if not db_manager.connect():
    #     print("Failed to connect to database.")
    #     return
    
    # # Ensure table exists (though we are only reading)
    # db_manager.create_table()
    # existing_cleaned_logs = db_manager.get_existing_cleaned_logs()
    # db_manager.close()
    
    # print(f"Loaded {len(existing_cleaned_logs)} existing cleaned logs from database.")

    # # 3. Filter and write unique raw lines to a new file
    # unique_lines = []
    
    unique_raw_lines = []
    
    with open(clean_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        file_lines = f.readlines()
        
    # Validation
    if len(file_lines) != len(all_log_content):
        print(f"Warning: Line count mismatch. File: {len(file_lines)}, Dict: {len(all_log_content)}")
        # If mismatch, we might have issues matching. But usually they match if stage_one logic holds.
        min_len = min(len(file_lines), len(all_log_content))
    else:
        min_len = len(file_lines)
        
    skipped_count = 0
    
    for i in range(min_len):
        cleaned_log_key = all_log_content[i][0].strip()
        raw_line_from_file = file_lines[i].strip() # We strip whitespace but DO NOT split by ':'
        
        if cleaned_log_key not in existing_cleaned_logs:
            unique_raw_lines.append(raw_line_from_file)
            # Add to local set to handle duplicates within the current file itself
            existing_cleaned_logs.add(cleaned_log_key)
        else:
            skipped_count += 1
            
    # 4. Write to local file
    output_filename = f"filtered_unique_{os.path.basename(log_file_path)}"
    output_path = os.path.join(os.path.dirname(log_file_path), output_filename)
    
    with open(output_path, 'w', encoding='utf-8') as out_f:
        for line in unique_raw_lines:
            out_f.write(line + "\n")
            
    end_time = time.time()
    
    print(f"Filter completed in {end_time - start_time:.2f} seconds.")
    print(f"Total lines processed: {min_len}")
    print(f"Skipped (already in DB): {skipped_count}")
    print(f"New unique lines found: {len(unique_raw_lines)}")
    print(f"Unique lines written to: {output_path}")

    return clean_file_path, output_path

if __name__ == "__main__":
    clean_log()
