import sys
import os
import re
import json

# 添加当前目录到 sys.path 以便导入 extract_log_id
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import extract_log_id
except ImportError:
    # 如果从不同目录运行，尝试使用绝对路径
    sys.path.append('/home/amlogic/RAG/clean_log/store_filter_log')
    import extract_log_id

def extract_runtime_exception(log_file_path):
    crash_start_pattern = "FATAL EXCEPTION"
    crash_blocks = []
    
    current_block_info = None
    capturing = False
    target_tid = None
    line_number = 0
    
    # 正则表达式
    # 匹配 Process: com.package.name, PID: 1234
    process_pid_pattern = re.compile(r'Process:\s+(.+?),\s+PID:\s+(\d+)')
    
    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            for line in f:
                line_number += 1
                
                # 获取当前行的日志信息（TID等）
                log_info = extract_log_id.extract_log_info(line)
                current_tid = log_info.get('thread_id')
                
                # 检查 crash 开始标志 (不区分大小写)
                if crash_start_pattern.lower() in line.lower():
                    # 如果之前正在捕获，先结束之前的块
                    if capturing and current_block_info:
                        crash_blocks.append(current_block_info)
                        current_block_info = None
                    
                    # 开始新的捕获
                    capturing = True
                    target_tid = current_tid
                    current_block_info = {
                        "lines": [line],
                        "start_line": line_number,
                        "end_line": line_number,
                        "tid": target_tid,
                        "process_name": "Unknown",
                        "pid": "Unknown"
                    }
                    continue
                
                # 如果处于捕获状态
                if capturing:
                    # 如果当前行的 TID 与崩溃的 TID 一致
                    if current_tid == target_tid and "AndroidRuntime" in line:
                        current_block_info["lines"].append(line)
                        current_block_info["end_line"] = line_number
                        
                        # 尝试提取 Process Name 和 PID
                        # 格式: Process: com.example.sampleleanbacklauncher, PID: 1454
                        if current_block_info["pid"] == "Unknown":
                            match = process_pid_pattern.search(line)
                            if match:
                                current_block_info["process_name"] = match.group(1)
                                current_block_info["pid"] = match.group(2)

            # 文件结束，保存最后一个块
            if capturing and current_block_info:
                crash_blocks.append(current_block_info)

    except Exception as e:
        # 在主函数中处理错误，或者返回空列表
        return []
        
    results = []
    for block in crash_blocks:
        crash_entry = {
            "file_name": log_file_path,
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "process_name": block["process_name"],
            "pid": block["pid"],
            "full_stack_trace": "".join(block["lines"])
        }
        results.append(crash_entry)
        
    return results

def extract_native_backtrace(log_file_path):
    """
    提取类似于以下的 native crash backtrace:
    12-30 16:46:22.954 D/SubtitleService( 2781): #00 pc 00011819  /vendor/bin/hw/subtitleserver ...
    """
    crash_blocks = []
    
    current_block_info = None
    capturing = False
    target_tid = None
    line_number = 0
    
    # 正则表达式
    # 匹配: ... #00 pc ...
    # 我们需要更通用的匹配，因为每一行都是 #XX pc ...
    # 关键是检测 #00 pc 开头，这标志着新的堆栈开始
    start_pattern = re.compile(r'#00\s+pc\s+[0-9a-fA-F]+')
    
    # 匹配后续的堆栈行: #01 pc ... #02 pc ...
    stack_line_pattern = re.compile(r'#\d{2}\s+pc\s+[0-9a-fA-F]+')

    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            for line in f:
                line_number += 1
                
                # 获取当前行的日志信息（TID等）
                log_info = extract_log_id.extract_log_info(line)
                current_tid = log_info.get('thread_id')
                
                # 检查是否是堆栈开始 (#00 pc)
                match_start = start_pattern.search(line)
                
                if match_start:
                    # 如果之前正在捕获，并且 TID 不同，说明之前的结束了（或者同一个 TID 新的 crash）
                    if capturing and current_block_info:
                        crash_blocks.append(current_block_info)
                        current_block_info = None
                    
                    # 开始新的捕获
                    capturing = True
                    target_tid = current_tid
                    current_block_info = {
                        "lines": [line],
                        "start_line": line_number,
                        "end_line": line_number,
                        "tid": target_tid,
                        "process_name": "Unknown",
                        "pid": "Unknown" # 对于这种格式，通常 PID 在括号里，例如 ( 2781)
                    }
                    
                    # 尝试从当前行提取 PID/Process Name (如果格式中有)
                    # Example: D/SubtitleService( 2781):
                    # Tag: SubtitleService, PID: 2781
                    # 我们可以尝试提取 Tag 作为 Process Name 候选，括号里的数字作为 PID
                    tag_pid_match = re.search(r'([A-Za-z0-9_]+)\(\s*(\d+)\):', line)
                    if tag_pid_match:
                         current_block_info["process_name"] = tag_pid_match.group(1)
                         current_block_info["pid"] = tag_pid_match.group(2)
                    
                    continue
                
                # 如果处于捕获状态
                if capturing:
                    # 检查是否是堆栈行
                    match_stack = stack_line_pattern.search(line)
                    
                    if match_stack and current_tid == target_tid:
                        current_block_info["lines"].append(line)
                        current_block_info["end_line"] = line_number


            # 文件结束，保存最后一个块
            if capturing and current_block_info:
                crash_blocks.append(current_block_info)

    except Exception as e:
        return []
        
    results = []
    for block in crash_blocks:
        crash_entry = {
            "file_name": log_file_path,
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "process_name": block["process_name"],
            "pid": block["pid"],
            "full_stack_trace": "".join(block["lines"])
        }
        results.append(crash_entry)
        
    return results

def extract_java_exception(log_file_path):
    """
    提取 Java Exception (e.g., java.lang.xxxException)
    识别模式:
    1. 开始行包含 "java.lang.xxxException" (或类似)
    2. 后续行包含 "at com.xxx" 并且 TID 相同
    """
    crash_blocks = []
    
    current_block_info = None
    capturing = False
    target_tid = None
    line_number = 0
    
    # 正则表达式
    # 匹配 Exception 开始: java.lang.xxxException 或其他全限定名 Exception
    # 简单起见，匹配 "java.lang." 后面跟一些字符，然后 "Exception"
    # 或者更通用一点，匹配常见异常格式。用户指定 "java.lang.xxxException"
    # 我们使用 regex: java\.lang\.[a-zA-Z0-9_$]+Exception
    exception_start_pattern = re.compile(r'java\.lang\.[a-zA-Z0-9_$]+Exception')
    
    # 匹配堆栈行: at package.class.method(...)
    # 注意日志前面可能有时间戳等，所以匹配 " at "
    stack_trace_pattern = re.compile(r'\s+at\s+[a-zA-Z0-9_$.]+\(')
    
    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            for line in f:
                line_number += 1
                
                # 获取当前行的日志信息（TID等）
                log_info = extract_log_id.extract_log_info(line)
                current_tid = log_info.get('thread_id')
                
                # 检查是否是 Exception 开始
                match_start = exception_start_pattern.search(line)
                
                # 有时候 FATAL EXCEPTION 也会包含 java.lang.Exception，为了避免重复，
                # 我们可能需要检查这行是否已经被 FATAL EXCEPTION 处理过。
                # 但这里是独立的函数，我们先独立提取，最后合并时可能需要去重（如果重叠）。
                # 不过 FATAL EXCEPTION 通常由 AndroidRuntime 打印，格式略有不同。
                # System.err 打印的通常是 W/System.err
                
                if match_start:
                    # 如果之前正在捕获，并且 TID 不同，说明之前的结束了
                    if capturing and current_block_info:
                        crash_blocks.append(current_block_info)
                        current_block_info = None
                    
                    # 开始新的捕获
                    capturing = True
                    target_tid = current_tid
                    current_block_info = {
                        "lines": [line],
                        "start_line": line_number,
                        "end_line": line_number,
                        "tid": target_tid,
                        "process_name": "Unknown",
                        "pid": "Unknown"
                    }
                    
                    # 尝试从 Tag 中提取 PID (如 System.err( 2985))
                    tag_pid_match = re.search(r'([A-Za-z0-9_./]+)\(\s*(\d+)\):', line)
                    if tag_pid_match:
                         # System.err 不是进程名，但我们可以先存着，或者标记为未知
                         # 这里我们存 Tag
                         current_block_info["process_name"] = tag_pid_match.group(1) 
                         current_block_info["pid"] = tag_pid_match.group(2)
                    
                    continue
                
                if capturing:
                    # 检查是否是堆栈行 (at ...)
                    match_stack = stack_trace_pattern.search(line)
                    
                    if match_stack and current_tid == target_tid:
                        current_block_info["lines"].append(line)
                        current_block_info["end_line"] = line_number


            # 文件结束
            if capturing and current_block_info:
                crash_blocks.append(current_block_info)

    except Exception as e:
        return []

    results = []
    for block in crash_blocks:
        crash_entry = {
            "file_name": log_file_path,
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "process_name": block["process_name"],
            "pid": block["pid"],
            "full_stack_trace": "".join(block["lines"])
        }
        results.append(crash_entry)
        
    return results

def extract_keywords_log(log_file_path):
    """
    提取包含特定关键词的日志 (e.g., "tombstoned", "avc: denied")
    这里不需要像 crash 那样提取堆栈，只需要提取单行或相关的行。
    但为了保持格式一致，我们将每行匹配的日志作为一个独立的 entry。
    或者如果它们是连续的，可以合并？通常 avc denied 是单行的，tombstoned 也是。
    """
    keywords = ["tombstoned:", "/system/bin/tombstoned"]
    crash_blocks = []
    
    line_number = 0
    
    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            for line in f:
                line_number += 1
                
                # 检查是否包含关键词
                found_keyword = False
                for kw in keywords:
                    if kw in line:
                        found_keyword = True
                        break
                
                if found_keyword:
                    # 尝试提取 PID/Process Name
                    # 常见的 avc: denied 格式:
                    # ... avc: denied { ... } for pid=1234 comm="process_name" ...
                    pid = "Unknown"
                    process_name = "Unknown"
                    
                    # AVC specific extraction
                    if "avc: denied" in line:
                        pid_match = re.search(r'pid=(\d+)', line)
                        if pid_match:
                            pid = pid_match.group(1)
                        
                        comm_match = re.search(r'comm="([^"]+)"', line)
                        if comm_match:
                            process_name = comm_match.group(1)
                    else:
                        # 对于其他日志，尝试使用标准 Logcat 提取
                        log_info = extract_log_id.extract_log_info(line)
                        # 这里 extract_log_id 返回的是 TID，不一定是 PID。
                        # 但我们可以尝试解析 Tag( PID) 格式
                        tag_pid_match = re.search(r'\(\s*(\d+)\):', line)
                        if tag_pid_match:
                            pid = tag_pid_match.group(1)
                    
                    crash_entry = {
                        "lines": [line],
                        "start_line": line_number,
                        "end_line": line_number,
                        "process_name": process_name,
                        "pid": pid
                    }
                    crash_blocks.append(crash_entry)

    except Exception as e:
        return []

    results = []
    for block in crash_blocks:
        crash_entry = {
            "file_name": log_file_path,
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "process_name": block["process_name"],
            "pid": block["pid"],
            "full_stack_trace": "".join(block["lines"])
        }
        results.append(crash_entry)
        
    return results

def extract_debug_crash(log_file_path):
    crash_start_pattern = "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***"
    crash_blocks = []
    
    # 存储 crash 信息： { "lines": [], "start_line": int, "end_line": int }
    current_block_info = None 
    
    capturing = False
    debug_id = None
    line_number = 0
    
    # 预编译正则，用于在 dump 中查找崩溃的 PID
    # 格式: pid: 2823, tid: 7179, name: Binder:2823_3  >>> /system/bin/mediaserver <<<
    pid_pattern = re.compile(r'pid:\s*(\d+),\s*tid:\s*(\d+),')

    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            for line in f:
                line_number += 1
                # 解析行以获取 ID
                log_info = extract_log_id.extract_log_info(line)
                line_id = log_info.get('thread_id')
                
                # 检查 crash 开始标志
                if crash_start_pattern in line:
                    # 如果已经在捕获中，保存之前的块
                    if capturing and current_block_info:
                        crash_blocks.append(current_block_info)
                        current_block_info = None
                    
                    capturing = True
                    debug_id = line_id
                    current_block_info = {
                        "lines": [line],
                        "debug_id": debug_id,
                        "start_line": line_number,
                        "end_line": line_number # 初始化，稍后更新
                    }
                    continue
                
                if capturing:
                    # 如果 ID 匹配 DEBUG 进程 ID，继续收集
                    if line_id == debug_id and ("DEBUG" in line or "F/DEBUG" in line):
                        current_block_info["lines"].append(line)
                        current_block_info["end_line"] = line_number
                    # 如果不匹配，可能是另一个进程的交错日志，忽略
            
            # End of file
            if capturing and current_block_info:
                crash_blocks.append(current_block_info)
                
    except Exception as e:
        print(json.dumps({"error": f"Error reading file: {e}"}, ensure_ascii=False))
        return

    # Process results into JSON format
    results = []
    
    for block in crash_blocks:
        block_lines = block["lines"]
        # Identify crashing PID
        crashing_pid = "Unknown"
        process_name = "Unknown"
        
        full_stack = "".join(block_lines)
        
        # 尝试从堆栈信息中提取 PID 和进程名
        for line in block_lines:
            match = pid_pattern.search(line)
            if match:
                crashing_pid = match.group(1)
                name_match = re.search(r'>>>\s+(.+?)\s+<<<', line)
                if name_match:
                    process_name = name_match.group(1)
                break
        
        crash_entry = {
            "file_name": log_file_path,
            "start_line": block["start_line"],
            "end_line": block["end_line"],
            "process_name": process_name,
            "pid": crashing_pid,
            "full_stack_trace": full_stack
        }
        results.append(crash_entry)
    
    return results

def extract_kernel_panic(log_file_path):
    """
    提取 Kernel Panic 信息
    逻辑：
    1. 找到 "Kernel panic" 关键字所在的行作为结束点。
    2. 从该结束点往前回溯，找到最近的 "Hardware name" 关键字所在的行作为起始点。
    3. 提取这两行之间的所有内容。
    """
    panic_blocks = []
    
    # 关键字
    panic_keyword = "Kernel panic"
    hardware_name_keyword = "Hardware name"
    
    try:
        with open(log_file_path, 'r', errors='ignore') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        
        # 遍历所有行查找 "Kernel panic"
        for i in range(total_lines):
            line = lines[i]
            
            # 1. 发现 Kernel panic
            if panic_keyword in line:
                panic_end_index = i
                panic_start_index = -1
                
                # 2. 往前回溯找 Hardware name
                # 我们设定一个合理的最大回溯行数，防止无限回溯（例如 200 行）
                MAX_LOOKBACK = 200 
                for j in range(panic_end_index, max(-1, panic_end_index - MAX_LOOKBACK), -1):
                    if hardware_name_keyword in lines[j]:
                        panic_start_index = j
                        break
                
                # 如果没找到 Hardware name，尝试找 "Unable to handle kernel" 或 "Internal error" 作为备选起始点
                # 或者直接取 panic 前面若干行
                if panic_start_index == -1:
                     # 备选策略：如果找不到 Hardware name，尝试回溯到 ---[ cut here ]--- 或者类似的分割线
                     # 这里暂时只实现用户要求的 Hardware name
                     pass

                if panic_start_index != -1:
                    # 提取块
                    # 包含 Hardware name 行，也包含 Kernel panic 行，可能还需要包含 panic 后面的几行（如 SMP stopping）
                    # 用户示例中 panic 在倒数第二行，后面还有 SMP stopping。
                    # 我们可以多取 panic 后面的几行，例如 5 行，或者直到文件结束
                    
                    extra_lines_after = 6
                    real_end_index = min(total_lines - 1, panic_end_index + extra_lines_after)
                    
                    block_lines = lines[panic_start_index : real_end_index + 1]
                    full_stack = "".join(block_lines)
                    
                    # 提取一些元数据
                    process_name = "kernel"
                    pid = "unknown"
                    
                    # 尝试从 Hardware name 行或者后续行提取一些信息 (可选)
                    # [  206.826574][0 T248   d.] CPU: 0 PID: 248 Comm: surfaceflinger
                    # 通常 Hardware name 上面一行会有 CPU/PID/Comm 信息
                    if panic_start_index > 0:
                        prev_line = lines[panic_start_index - 1]
                        if "PID:" in prev_line and "Comm:" in prev_line:
                            pid_match = re.search(r'PID:\s*(\d+)', prev_line)
                            comm_match = re.search(r'Comm:\s+(\S+)', prev_line)
                            if pid_match: pid = pid_match.group(1)
                            if comm_match: process_name = comm_match.group(1)

                    crash_entry = {
                        "file_name": log_file_path,
                        "start_line": panic_start_index + 1,
                        "end_line": real_end_index + 1,
                        "process_name": process_name,
                        "pid": pid,
                        "full_stack_trace": full_stack,
                        "crash_type": "kernel_panic"
                    }
                    panic_blocks.append(crash_entry)
                    
    except Exception as e:
        print(json.dumps({"error": f"Error reading file in extract_kernel_panic: {e}"}, ensure_ascii=False))
        return []

    return panic_blocks

def extract_crash(log_file_path):
    debug_results = extract_debug_crash(log_file_path)
    if debug_results is None: debug_results = []
    
    runtime_results = extract_runtime_exception(log_file_path)
    if runtime_results is None: runtime_results = []
    
    native_results = extract_native_backtrace(log_file_path)
    if native_results is None: native_results = []
    
    kernel_panic_results = extract_kernel_panic(log_file_path)
    if kernel_panic_results is None: kernel_panic_results = []
    
    # java_results = extract_java_exception(log_file_path)
    # if java_results is None: java_results = []
    java_results = []
    
    keyword_results = extract_keywords_log(log_file_path)
    if keyword_results is None: keyword_results = []
    
    all_results = debug_results + runtime_results + native_results + java_results + keyword_results + kernel_panic_results
    
    extracted_crashes_path = os.path.join(os.path.dirname(log_file_path), f"extracted_crashes_{os.path.basename(log_file_path)}.json")
    with open(extracted_crashes_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"Extracted crashes saved to: {extracted_crashes_path}")
    return all_results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # print("用法: python extract_crash.py <log_file>")
        print(json.dumps({"error": "Usage: python extract_crash.py <log_file>"}, ensure_ascii=False))
        sys.exit(1)
    
    log_file = sys.argv[1]
    if not os.path.exists(log_file):
        # print(f"文件未找到: {log_file}")
        print(json.dumps({"error": f"File not found: {log_file}"}, ensure_ascii=False))
        sys.exit(1)
        
    results = extract_crash(log_file)
    
    # Output JSON
    print(json.dumps(results, indent=4, ensure_ascii=False))
