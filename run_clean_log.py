import os
import sys
import time
# 添加项目根目录到 sys.path，以便能导入 utils
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from clean_log.utils import clean_log_stage_one_multi

def main():
    # 目标日志文件路径
    log_file_path = "/home/amlogic/RAG/clean_log/咪咕极速节目详情页语音收点播节目，播放返回报错.log"
    
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}")
        return

    # 解析目录和文件名
    src_dir = os.path.dirname(log_file_path)
    file_name = os.path.basename(log_file_path)
    
    # 定义输出目录 (和源文件同一目录)
    dest_dir = src_dir
    
    # 准备重复行 map (空列表)
    duplicate_map_list = []
    start_time = time.time()
    print(f"Starting to clean log file: {log_file_path}")
    
    # 调用清洗函数
    clean_file_path, all_log_content = clean_log_stage_one_multi(src_dir, file_name, dest_dir, duplicate_map_list)
    save_db_raw_log = []
    with open (clean_file_path, 'r') as f:
        lines = f.readlines()
        for index, line in enumerate(lines):

            # print(f"all_log_content[{index}]: {all_log_content[index]}")
            raw_log = line.split(':', 1)[1].strip() if ':' in line else line.strip()
            save_db_raw_log.append(raw_log)
            if index < 10:
                print(f"line[{index}]: {raw_log}")

    # 打印前 10 个字典项
    print(f"First 10 items of all_log_content:")
    save_db_raw_log_re = []
    
    # 按照 value (行号) 排序，确保顺序与文件读取顺序一致  
    for i, (key, value) in enumerate(all_log_content):
        if i < 10:
            print(f"all_log_content[{i}]: ({key.strip()}:{value})")
        # 收集所有的 key，作为清洗后的日志内容
        save_db_raw_log_re.append(key.strip())
    
    # 将两个列表存储到 sqlite3 数据库
    import sqlite3
    db_path = os.path.join(dest_dir, "log_data.db")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS log_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cleaned_log TEXT,
                raw_log TEXT
            )
        ''')
        
        # 创建索引以加速查询
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cleaned_log ON log_records(cleaned_log)')
        
        print(f"save_db_raw_log_re: {len(save_db_raw_log_re)}")
        print(f"save_db_raw_log: {len(save_db_raw_log)}")
        # 确保两个列表长度一致，取最小长度以防越界
        min_len = min(len(save_db_raw_log_re), len(save_db_raw_log))
        
        # 批量插入数据（带去重检查）
        data_to_insert = []
        skipped_count = 0
        
        # 预先查询数据库中已存在的 cleaned_log，使用集合加速查找
        # 注意：如果数据量巨大，可能需要分批查询或使用 Bloom Filter，这里假设内存足够
        cursor.execute("SELECT cleaned_log FROM log_records")
        existing_cleaned_logs = set(row[0] for row in cursor.fetchall())
        
        for i in range(min_len):
            cleaned_log = save_db_raw_log_re[i]
            raw_log = save_db_raw_log[i]
            
            if cleaned_log not in existing_cleaned_logs:
                data_to_insert.append((cleaned_log, raw_log))
                # 更新本地缓存集合，防止本次批量插入中有重复项（虽然 save_db_raw_log_re 本身应该已去重，但双重保险）
                existing_cleaned_logs.add(cleaned_log)
            else:
                skipped_count += 1
            
        if data_to_insert:
            cursor.executemany('INSERT INTO log_records (cleaned_log, raw_log) VALUES (?, ?)', data_to_insert)
            conn.commit()
            print(f"Successfully saved {len(data_to_insert)} new records to database: {db_path}")
        else:
            print("No new records to insert.")
            
        if skipped_count > 0:
            print(f"Skipped {skipped_count} existing records.")
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()
    
    
        
    
    end_time = time.time()
    print(f"Log cleaning completed in {end_time - start_time:.2f} seconds.")
    
    if clean_file_path and os.path.exists(clean_file_path):
        print(f"Successfully cleaned log. Output file: {clean_file_path}")
    else:
        print("Log cleaning failed.")

if __name__ == "__main__":
    main()
