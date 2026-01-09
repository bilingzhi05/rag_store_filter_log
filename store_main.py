import os
import time
import sys
from datetime import datetime
import csv
from log_cleaner import LogCleaner
from database_manager import DatabaseManager

def main():
    # Target log file path
    log_file_path = "/home/amlogic/RAG/clean_log/store_log_data/OTT-59458/success/XA-OTT-59458-Subtitle-CC_display_abnormal-resolved.txt.txt"
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}")
        return

    start_time = time.time()

    # 1. Clean the log
    cleaner = LogCleaner(log_file_path)
    clean_file_path, all_log_content = cleaner.clean_log()

    if not clean_file_path or not os.path.exists(clean_file_path):
        print("Log cleaning failed.")
        return

    # 2. Process cleaned data for DB insertion
    save_db_raw_log_re, save_db_raw_log = cleaner.process_cleaned_log(clean_file_path, all_log_content)

    # 3. Save to Database
    db_path = os.path.join("/home/amlogic/RAG/clean_log/store_log_data", "log_data.db")
    db_manager = DatabaseManager(db_path)
    
    if db_manager.connect():
        db_manager.create_table()
        
        print(f"save_db_raw_log_re: {len(save_db_raw_log_re)}")
        print(f"save_db_raw_log: {len(save_db_raw_log)}")
        
        min_len = min(len(save_db_raw_log_re), len(save_db_raw_log))
        
        existing_cleaned_logs = db_manager.get_existing_cleaned_logs()
        
        data_to_insert = []
        skipped_count = 0
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for i in range(min_len):
            cleaned_log = save_db_raw_log_re[i]
            raw_log = save_db_raw_log[i]
            
            if cleaned_log not in existing_cleaned_logs:
                data_to_insert.append((cleaned_log, raw_log, current_time))
                existing_cleaned_logs.add(cleaned_log)
            else:
                skipped_count += 1
        
        # Save to CSV before inserting into database
        if data_to_insert:
            csv_file_path = os.path.join(os.path.dirname(log_file_path), f"insert_log_data_{os.path.basename(log_file_path)}.csv")
            try:
                with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Cleaned Log', 'Raw Log', 'Created At']) # Write header
                    writer.writerows(data_to_insert)
                print(f"Successfully saved {len(data_to_insert)} records to CSV: {csv_file_path}")
            except Exception as e:
                print(f"Error saving to CSV: {e}")

        inserted_count = db_manager.insert_records(data_to_insert)
        
        if inserted_count > 0:
            print(f"Successfully saved {inserted_count} new records to database: {db_path}")
        else:
            print("No new records to insert.")
            
        if skipped_count > 0:
            print(f"Skipped {skipped_count} existing records.")
            
        db_manager.close()

    end_time = time.time()
    print(f"Log cleaning completed in {end_time - start_time:.2f} seconds.")
    print(f"Successfully cleaned log. Output file: {clean_file_path}")

if __name__ == "__main__":
    main()
