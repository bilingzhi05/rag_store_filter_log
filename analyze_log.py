import os
import sys
# Add current directory to sys.path to ensure utils can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from utils import filter_log_errors

def main():
    log_file_path = "/home/amlogic/RAG/clean_log/XA-OTT-55203-AudioFramework-no audio for a while.log"
    
    if not os.path.exists(log_file_path):
        print(f"Error: File not found at {log_file_path}")
        return

    try:
        print(f"Analyzing file: {log_file_path}")
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        print(f"Read {len(lines)} lines.")
        
        # Call filter_log_errors
        filtered_lines = filter_log_errors(contents=lines)
        
        print(f"Found {len(filtered_lines)} relevant lines (errors/fails/etc.):")
        print("-" * 50)
        for line in filtered_lines:
            print(line.strip())
        print("-" * 50)
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
