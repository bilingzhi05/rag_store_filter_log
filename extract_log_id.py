import re

def extract_log_info(log_line):
    """
    识别日志格式并提取线程号/进程号
    支持格式:
    1. Logcat 格式 (timestamp PID TID LEVEL Tag: Message)
       Example: 01-04 07:07:55.737 10031  1454  1454 E AndroidRuntime: FATAL EXCEPTION: main
    
    2. Android Studio/System.err 格式 (timestamp LEVEL/Tag( PID): Message)
       Example: 12-30 16:47:12.862 W/System.err( 2985): java.lang.IllegalArgexceumentException...
    """
    
    # 格式1: 01-04 07:07:55.737 10031  1454  1454 E AndroidRuntime: FATAL EXCEPTION: main
    # 匹配: date time PID TID TID LEVEL Tag: Message
    # 注意: 有些变体可能只有一个 TID，或者 PID TID 顺序不同，这里针对给出的例子适配
    # 例子中: 10031(UID?) 1454(PID) 1454(TID) ? 或者是 PID TID TID?
    # 通常 logcat -v threadtime 格式: date time PID TID Level Tag: Message
    # 例子: 01-04 07:07:55.737 10031  1454  1454 E ...
    # 看起来像是: date time UID PID TID Level ... 或者 date time PID TID TID Level ...
    # 我们假设中间两个或三个数字中，紧跟在 LEVEL 前面的是 TID，再前面是 PID
    
    # Pattern 1: Logcat threadtime-like format
    # 匹配: date time ... (2或3个数字) ... Level
    # 提取目标: 紧跟在 Level 前面的那个数字 (TID)
    # 使用非捕获组 (?:\d+\s+){1,2} 来匹配前面的1个或2个数字，然后捕获最后一个数字
    pattern1 = re.compile(r'^\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+(?:\d+\s+){1,2}(\d+)\s+[A-Z]\s+')
    match1 = pattern1.search(log_line)
    if match1:
        return {
            "type": "Logcat (ThreadTime extended)",
            "thread_id": match1.group(1) # 提取 Level 前的最后一个数字作为 TID
        }

    # Pattern 2: Android Studio / Logcat brief-like with PID
    # 12-30 16:47:12.862 W/System.err( 2985): ...
    # 匹配: date time Level/Tag( PID): ...
    pattern2 = re.compile(r'^\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+[A-Z]/[^:]+\(\s*(\d+)\):')
    match2 = pattern2.search(log_line)
    if match2:
        return {
            "type": "Logcat (Brief/Process)",
            "thread_id": match2.group(1)
        }
        
    return {"type": "Unknown", "thread_id": None}

def main():
    test_logs = [
        "01-04 07:07:55.737 10031  1454  1454 E AndroidRuntime: FATAL EXCEPTION: main",
        "12-30 16:47:12.862 W/System.err( 2985): java.lang.IllegalArgexceumentException: Wake lock not active: android.os.BinderProxy@d2c3544 from uid 1041"
    ]
    
    print("Testing Log Extraction:")
    print("-" * 50)
    
    for log in test_logs:
        print(f"Log: {log.strip()}")
        result = extract_log_info(log)
        print(f"Result: {result}")
        print("-" * 50)

if __name__ == "__main__":
    main()
