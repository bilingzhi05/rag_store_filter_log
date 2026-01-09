import sqlite3
import os

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            return True
        except sqlite3.Error as e:
            print(f"SQLite connection error: {e}")
            return False

    def create_table(self):
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cleaned_log TEXT,
                    raw_log TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Check if created_at column exists, if not add it (for existing databases)
            self.cursor.execute("PRAGMA table_info(log_records)")
            columns = [info[1] for info in self.cursor.fetchall()]
            if 'created_at' not in columns:
                print("Adding 'created_at' column to existing table...")
                self.cursor.execute('ALTER TABLE log_records ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_cleaned_log ON log_records(cleaned_log)')
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating table: {e}")

    def get_existing_cleaned_logs(self):
        try:
            self.cursor.execute("SELECT cleaned_log FROM log_records")
            return set(row[0] for row in self.cursor.fetchall())
        except sqlite3.Error as e:
            print(f"Error fetching existing logs: {e}")
            return set()

    def insert_records(self, data_to_insert):
        if not data_to_insert:
            return 0
        try:
            # Check if input data has 2 or 3 elements per record
            if len(data_to_insert[0]) == 3:
                self.cursor.executemany('INSERT INTO log_records (cleaned_log, raw_log, created_at) VALUES (?, ?, ?)', data_to_insert)
            else:
                self.cursor.executemany('INSERT INTO log_records (cleaned_log, raw_log) VALUES (?, ?)', data_to_insert)
                
            self.conn.commit()
            return len(data_to_insert)
        except sqlite3.Error as e:
            print(f"Error inserting records: {e}")
            return 0

    def close(self):
        if self.conn:
            self.conn.close()
