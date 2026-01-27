import os
import sys

# Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils import clean_log_stage_one_multi, convert_file_to_utf8

class LogCleaner:
    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        # Ensure file is utf-8 before processing
        convert_file_to_utf8(self.log_file_path)
        
        self.src_dir = os.path.dirname(log_file_path)
        self.file_name = os.path.basename(log_file_path)
        self.dest_dir = self.src_dir
        self.duplicate_map_list = []

    def clean_log(self):
        print(f"Starting to clean log file: {self.log_file_path}")
        clean_file_path, all_log_content = clean_log_stage_one_multi(
            self.src_dir, self.file_name, self.dest_dir, self.duplicate_map_list
        )
        return clean_file_path, all_log_content

    def process_cleaned_log(self, clean_file_path, all_log_content):
        save_db_raw_log = []
        save_db_raw_log_re = []

        # Process raw logs from the cleaned file
        with open(clean_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for index, line in enumerate(lines):
                raw_log = line.split(':', 1)[1].strip() if ':' in line else line.strip()
                save_db_raw_log.append(raw_log)
                if index < 10:
                    print(f"line[{index}]: {raw_log}")

        print(f"First 10 items of all_log_content:")
        
        # process cleaned logs
        for i, (key, value) in enumerate(all_log_content):
            if i < 10:
                print(f"all_log_content[{i}]: ({key.strip()}:{value})")
            save_db_raw_log_re.append(key.strip())

        return save_db_raw_log_re, save_db_raw_log
