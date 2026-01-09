
import os
import re
import concurrent.futures 
import time

import zipfile
import tarfile
from jinja2.nodes import Break
# import py7zr

# import rarfile

import shutil
import re
import os
from typing import List
from transformers import AutoTokenizer
# from common.config import LOG_FETCHER_MAX_LINE_CHAR_LENGTH
LOG_FETCHER_MAX_LINE_CHAR_LENGTH = 100000


#剔除markdown文本的开头和结尾的···和markdown标记
def remove_markdown_code(text: str) -> str:
    if not text:
        return ""
    m = re.match(r'^\s*```markdown[^\n]*\n([\s\S]*?)\n?```\s*$', text)
    if m:
        return m.group(1).strip()
    return text.strip()

# # 加载 Qwen tokenizer
# tokenizer = AutoTokenizer.from_pretrained("qwen/Qwen-7B-Chat")  # 或替换为你要的 Qwen 模型

# def count_tokens(text: str) -> int:
#     tokens = tokenizer.encode(text)
#     return len(tokens)

#传入一个class_type输出对应的调试说明及链接
def get_class_type_debug_info(class_type: str) -> str:
    if class_type == "class_3":
        return "https://confluence.amlogic.com/pages/viewpage.action?pageId=323849191"
    elif class_type == "class_6":
        return "https://confluence.amlogic.com/pages/viewpage.action?pageId=560403529"
    elif class_type == "class_7":
        return "https://confluence.amlogic.com/pages/viewpage.action?pageId=630283356"
    else:
        return ""

#一个截取字符串内容的函数，入参是一段字符串以及希望保留的字符串长度，以及截断模式，模式有两种一种是按照行为单位截取，另一种是按照字符数截取，截取逻辑要从前往后累加字符数，保证不超入参的阈值
def truncate_content(text: str, max_length: int, mode: str = "line") -> str:
    if not text or max_length <= 0:
        return ""
    if mode == "char":
        return text[:max_length]
    total = 0
    out = []
    for line in text.splitlines(True):
        l = len(line)
        if total + l <= max_length:
            out.append(line)
            total += l
        else:
            if not out:
                out.append(line[:max_length])
            break
    return "".join(out)

# 写一个函数，入参是文件路径列表、正则表达式， 返回一个map数组结构，每个map中包含file、match_lines两个内容，
# file是文件路径，match_lines是一个数组，包含所有匹配的行内容
def find_match_lines_in_files(
    file_paths: List[str],
    regex: str,
    context_lines: int = 0,
    direction: str = "both"
) -> List[dict]:
    """
    在多个文件中查找匹配正则表达式的行，并提取上下文。

    参数:
        file_paths (List[str]): 文件路径列表，每个元素为一个字符串
        regex (str): 正则表达式字符串，用于匹配行内容
        context_lines (int): 需要额外提取的上下文行数，默认为 0
        direction (str): 提取方向，可选值为 'up'、'down'、'both'，默认为 'both'

    返回:
        List[dict]: 匹配结果列表，每个元素为一个字典，包含 'file' (文件路径) 和 'match_lines' (匹配行内容列表) 两个键值对，
                    其中 match_lines 中每项格式为 "line 行号: 行内容"
    """
    import subprocess
    import os

    results = []

    for file_path in file_paths:
        # 构造 findstr 命令（Windows）或 sed 命令（Linux/Mac）
        # 这里以 Windows 的 findstr 为例，Linux/Mac 可改用 sed
        # 由于 findstr 不支持上下文行数，这里仅做简单匹配，如需上下文需用 sed 或 grep -A -B
        try:
            if os.name == 'nt':  # Windows
                # findstr 不支持上下文，仅匹配行
                cmd = ['findstr', '/N', '/R', regex, file_path]
                completed = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                if completed.returncode == 0:
                    match_entries = []
                    #打开文件，读取所有行
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    for line in completed.stdout.strip().splitlines():
                        # 格式为 行号:内容
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            line_num, content = parts
                            # 提取上下文
                            start_line = max(0, int(line_num) - context_lines - 1)
                            end_line = min(len(lines), int(line_num) + context_lines)
                            # match_entries.append(f"line {line_num}: {content.strip()}")
                            # 添加上下文行
                            for i in range(start_line, end_line):
                                match_entries.append(f"line {i+1}: {lines[i].strip()}")
                    if match_entries:
                        results.append({"file": file_path, "match_lines": match_entries})
            else:  # Linux/Mac
                # 使用 grep -n -A -B 实现上下文
                up_arg = f"-B {context_lines}" if direction in ('up', 'both') else ''
                down_arg = f"-A {context_lines}" if direction in ('down', 'both') else ''
                cmd = f"grep -n -E '{regex}' {up_arg} {down_arg} {file_path}"
                completed = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                if completed.returncode == 0:
                    match_entries = []
                    for line in completed.stdout.strip().splitlines():
                        # 格式为 行号-内容 或 行号:内容
                        if line.startswith('--'):
                            continue
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            line_num, content = parts
                            match_entries.append(f"line {line_num}: {content.strip()}")
                    if match_entries:
                        results.append({"file": file_path, "match_lines": match_entries})
        except Exception as e:
            print(f"读取文件 {file_path} 时出错: {e}")
            continue

    return results

import re

def extract_kernel_crash_block(log_path: str) -> list[str]:
    """
    从给定的日志文件路径中提取 kernel panic/oops 的完整堆栈块。

    参数:
        log_path (str): 日志文件路径

    返回:
        list[str]: 每个元素为一个完整的 panic/oops 块
    """
    lines = []
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"读取文件 {log_path} 时出错: {e}")
        return []
    blocks = []

    # panic/oops 的开头正则
    start_regex = re.compile(
        r"(Kernel panic|Internal error|Unable to handle kernel paging request|Oops:)",
        re.IGNORECASE
    )

    # panic/oops 的结束行
    end_regex = re.compile(
        r"(Modules linked in:|---\[ end trace)",
        re.IGNORECASE
    )

    in_block = False
    current = []

    for line in lines:
        # 匹配 panic / oops 开头
        if not in_block and start_regex.search(line):
            in_block = True

        if in_block:
            # 跳过大块内存Dump（常见格式：大量十六进制地址）
            if re.match(r"\s*[0-9a-fA-F]{8}[: ]", line):
                continue
            if re.match(r"\s*[0-9a-fA-F]{16}[: ]", line):
                continue

            current.append(line)

            # 结束条件
            if end_regex.search(line):
                blocks.append("\n".join(current))
                in_block = False
                current = []

    return blocks


def get_jira_file_path(jira_id: str) -> tuple[str, str]:
    """
    根据 Jira ID 生成下载和解压目录路径
    
    Args:
        jira_id: Jira 问题 ID
        
    Returns:
        tuple: (下载目录路径, 解压目录路径)
        如果 jira_id 为空，返回 (None, None)
    """
    if not jira_id:
        print("jira_id is empty.")
        return None, None
        
    download_dir = f"tmp/cache/{jira_id}/download"
    extract_dir = f"tmp/cache/{jira_id}/extract"
    return download_dir, extract_dir

def file_reader(file_path: str, start_line: int, end_line: int, max_lines: int = 20) -> str:
    """
    读取文件中指定范围的行内容。

    参数:
        file_path (str): 文件路径，字符串类型
        start_line (int): 起始行号（从1开始）
        end_line (int): 结束行号（包含该行）
        max_lines (int, 可选): 单次最大读取行数，默认50行

    返回:
        str: 包含文件路径、行范围及对应内容的字符串；若文件不存在、权限不足或范围非法，则返回错误提示
    """
    try:
        print(f"真实执行 FileReader: {file_path} {start_line}-{end_line}")
        if start_line == 0:
            start_line = 1
        file_path = str(file_path).strip()
        # 改进：使用绝对路径处理
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        
        # 改进：检查文件是否存在
        if not os.path.exists(file_path):
            return f"文件不存在: {file_path}"
        
        # 改进：检查文件是否可读
        if not os.access(file_path, os.R_OK):
            return f"文件无法读取: {file_path}"
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return f"行号范围无效，文件共{len(lines)}行，请求范围：{start_line}-{end_line}"
        
        # 限制一次最多读取 max_lines 行
        actual_end_line = min(end_line, start_line + max_lines - 1)
        result = "".join(lines[start_line - 1 : actual_end_line])
        print(f"文件: {file_path}\n行范围: {start_line}-{actual_end_line}\n")
        return f"文件: {file_path}\n行范围: {start_line}-{actual_end_line}\n内容:\n{result}"
        
    except UnicodeDecodeError:
        return f"文件编码错误，无法读取: {file_path}"
    except PermissionError:
        return f"权限不足，无法访问文件: {file_path}"
    except Exception as e:
        return f"读取文件出错: {e}"

def write_to_file_normal(file_path, data):
    try:
        with open(file_path, 'w',encoding="utf-8", errors="replace") as file:
            for i, line in enumerate(data):
                # values = line.split('\t')
                file.write(line)
    except FileNotFoundError:
        print(f'{file_path} not found!')
    except IOError:
        print(f'{file_path} IOError occurred!')
    except Exception as e:
        print("An unexcepted error occured:",e)

def clean_stop_words(input_text):
    # 获取英文停用词列表
    stop_words = {'had', 'during', 'ma', 'having', 'over', 's', 'where', 'aren', 'its', 'my', 'we', "you're", 'against', "hasn't", 'because', 'there', 'should', 'from', "isn't", 'under', 'about', 'isn', 'below', 'm', 'did', 'or', 'to', "haven't", 'same', 've', 'have', 'you', 'ourselves', 'through', "wouldn't", 'yourselves', 'that', 'it', "aren't", 'just', "wasn't", 'does', 'nor', "hadn't", 'itself', 'o', 'being', 'but', 'off', 'the', 'not', 'than', "should've", 'once', 'ain', 'down', 'whom', 'more', 'here', 'while', 'wouldn', 'who', 'hadn', 'such', 'them', 'why', 'his', 'she', 'shan', "shan't", 'doesn', 'your', 'between', 'few', "mightn't", 'mightn', 'these', 'above', 'her', 'and', "you've", 'a', 'any', 'll', 'by', 'hasn', 'before', "you'd", 'again', 'after', 'into', 'now', "that'll", 'herself', 'do', 'am', 'with', 'both', 'their', 'too', 'shouldn', 'd', 'yourself', "shouldn't", 'on', 'of', 'at', "mustn't", 'for', "couldn't", 'himself', 'yours', "doesn't", 'haven', 'an', 'i', 'me', 'own', "won't", 'will', 'are', 're', "needn't", 'doing', 'ours', 'weren', 'which', 'y', "didn't", 'hers', "weren't", 'didn', 'our', 'other', 'each', 'those', 'this', 'needn', 'very', 'he', 'further', 'when', "you'll", 'in', 'they', 't', 'themselves', 'all', 'don', "she's", 'no', 'some', 'so', 'only', 'been', 'be', 'him', 'mustn', 'were', 'myself', 'was', 'wasn', 'won', "don't", 'what', 'until', 'if', 'is', 'as', 'out', 'can', 'most', 'couldn', 'theirs', 'up', 'then', "it's", 'how', 'has'}
    stop_words = set(stop_words)
    # 使用正则表达式分割文本为单词列表
    words = re.findall(r'\b\w+\b', input_text)

    # 过滤掉停用词
    meaningful_words = [word for word in words if word.lower() not in stop_words]

    # 重新组合单词为字符串
    cleaned_text = ' '.join(meaningful_words)
    return cleaned_text

def get_content_task_list(content_lines, max_workers = 30,files_per_iteration = 30000):
    grouped_files = []
    base_index = 0

    chrunk_size_split_min = len(content_lines)//max_workers
    files_per_iteration = chrunk_size_split_min
    if files_per_iteration < 30000:
        print(f'{files_per_iteration} is less than 5, set files_per_iteration to 5!')
        files_per_iteration = 30000

    if len(content_lines) == 0:
        print(f'get_content_task_list content is empty!')
        exit()

    while len(content_lines) > 0:
        grouped_files.append(list([content_lines[:files_per_iteration], base_index]))
        content_lines = content_lines[files_per_iteration:]
        base_index += files_per_iteration

    return grouped_files

#写一个日志清洗函数，输入日志文件路径，输出一个清洗后的日志文件路径，清洗规则为：1.去除空行，2.去除重复行，3.去除空格行，清洗前先去掉特殊字符和日志
def clean_log_stage_one_with_chrunk(file_name, content_lines, start_index, thread_id, duplicate_map_list):
    head_column_pattern = '[0-9-]+\s+[0-9:.]+\s+[0-9]+\s+[0-9]+\s+\w\s'
    number_pattern = r'(=0x[a-fA-F0-9]+|0x[a-fA-F0-9]+|=[a-fA-F0-9]+|\b[a-fA-F0-9]+\b)'
    delete_line = r'(http\:\/\/|rtsp\:\/\/|https\:\/\/)'
    special_symbol = r'([^a-zA-Z\r\n])'
    no_special_symbol_without_n = r'[^\S\n]+'
    log_tag_level = r'^\s[A-Z]\s'
    one_symbol = r'\b[a-zA-Z]\b'

    player_all_content = dict()
    count = start_index - 1

    total_size = len(content_lines)
    print(f"enter thread:{thread_id} ---->clean{file_name} [{start_index}~{total_size+count}]")
    start = time.time()
    for line in content_lines:
        count += 1
        if re.search(delete_line, line):
            continue
        modified_line = re.sub(head_column_pattern, '', line)
        modified_line = re.sub(number_pattern, '', modified_line)
        modified_line = re.sub(special_symbol, ' ', modified_line)
        modified_line = re.sub(one_symbol, ' ', modified_line)
        modified_line = re.sub(no_special_symbol_without_n, ' ', modified_line)
        modified_line = re.sub(log_tag_level, '', modified_line)
        modified_line = clean_stop_words(modified_line)
        modified_line += '\n'
        if modified_line in duplicate_map_list:
            continue
        player_all_content[modified_line] = count
        end = time.time()
    print(f"thread:{thread_id} ----<clean{file_name} [{start_index}~{total_size+count}] finished, cost time {end-start} s")
    return player_all_content


#写一个把打印的日志框起来显示的函数，输入日志内容，输出框起来的日志内容
def print_log_with_box(log_content, logger_object=None, log_level="debug"):
    if log_content is None or len(f"{log_content}".strip()) == 0:
        print("\n=========================================\n")
        print("log_content is empty!")
        print("\n=========================================\n")
    elif logger_object is None:
        print("\n=========================================\n")
        print(log_content)
        print("\n=========================================\n")
    else:
        if log_level == "debug":
            logger_object.debug("\n=========================================\n")
            logger_object.debug(log_content)
            logger_object.debug("\n=========================================\n")
        elif log_level == "info":
            logger_object.info("\n=========================================\n")
            logger_object.info(log_content)
            logger_object.info("\n=========================================\n")
        else:
            logger_object.error("\n=========================================\n")
            logger_object.error(log_content)
            logger_object.error("\n=========================================\n")

def filter_log_errors(contents:list[str] = [], output_dir: str = None, keywords: str = None) -> List[str]:
    """
    从日志文件中过滤出包含关键字的行，并在行首添加行号。
    同时可将结果输出到指定目录。

    参数:
        contents (list[str]): 输入的日志行数组
        output_dir (str): 输出目录（可选）。若为空则不写文件。
        keywords (List[str]): 匹配关键字列表，默认匹配 panic|error|failed|fail|not syncing

    返回:
        List[str]: 匹配到的日志行（带行号）
    """
    import numpy as np
    if keywords is None:
        keywords = r"error|fail|exception|panic|fatal|denied|crash|oops|segfault|abort|corrupt|not|dropped|err|disconnected|timeout|permission"

    # 构造匹配正则（忽略大小写）
    pattern = re.compile(r"error|fail|exception|panic|fatal|denied|crash|oops|segfault|abort|corrupt|not|dropped|err|disconnected|timeout|permission", re.IGNORECASE | re.UNICODE)

    # 读取日志文件
    lines = contents
    if len(lines) == 0:
        print_log_with_box("log file is empty")
        return []
    # 遍历每行匹配
    target_lines = [line for line in lines if pattern.search(line)]
        # 如果指定了输出目录，则保存结果文件
    # if output_dir:
    #     os.makedirs(output_dir, exist_ok=True)
    #     base_name = os.path.basename(log_path)
    #     output_path = os.path.join(output_dir, f"{base_name}")

    #     with open(output_path, "w", encoding="utf-8") as out:
    #         out.write("\n".join(target_lines))
    #         out.write("\n")

    # print(f"✅ 已保存过滤结果到: {output_path}")

    return target_lines
#todo需要检查超大文本的效果
def  clean_log_stage_one_multi(src_dir, file_name, dest_dir, duplicate_map_list):
    player_all_content = dict()
    clean_file_path = os.path.join(dest_dir, "clean_"+file_name)
    try:
        path = os.path.join(src_dir,file_name)
        print(f'clean {path}')
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            if not os.path.exists(dest_dir):
                print(f'build dir {dest_dir} failed!')
                return None
        with open(path, 'r', encoding="utf-8", errors="replace") as file:
            lines = file.readlines()
            total_lines = len(lines)
            print(f'{file_name} finish read lines\n')
            result_line_list = []
            content_lines_group = get_content_task_list(lines)
            print(f'finish get_content_task_list\n')
            with concurrent.futures.ProcessPoolExecutor(max_workers=10) as executor:
                results = [executor.submit(clean_log_stage_one_with_chrunk, file_name, content_lines[0], content_lines[1], thread_id, duplicate_map_list) for thread_id, content_lines in enumerate(content_lines_group)]
            # with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            #     results = [executor.submit(clean_log_stage_one_with_chrunk, file_name, content_lines[0], content_lines[1], thread_id, duplicate_map_list) for thread_id, content_lines in enumerate(content_lines_group)]
                for future in concurrent.futures.as_completed(results):
                    result = future.result()
                    player_all_content = result | player_all_content
            if player_all_content:
                print(f'write to clean_{file_name} \n')
                # 根据 index 从小到大排序并写入结果
                sorted_player_all_content = sorted(player_all_content.items(), key=lambda item: item[1])
                for _, index in sorted_player_all_content:
                    if 0 <= index < total_lines:
                        result_line_list.append(f"Line {index+1}: " + lines[index])
                result_lines = result_line_list
                # result_lines = filter_log_errors(result_line_list, None, None)
                write_to_file_normal(clean_file_path, result_lines)
            else:
                print(f'result is empty after clean!')
    except FileNotFoundError:
        print(f'{path} not found!')
    except IOError:
        print(f'{path} IOError occurred!')
    except Exception as e:
        print("clean_log_stage_one_multi An unexcepted error occured:",e)
    return clean_file_path, sorted_player_all_content
#提出字符串中<think></think>和中间包裹的内容
def extract_think_content(text):
    start_index = text.find("<think>") + len("<think>")
    end_index = text.find("</think>", start_index)
    return text[start_index:end_index].strip()
#剔除掉字符串中<think></think>和中间包裹的内容
def remove_think_content(text):
    start_index = text.find("<think>")
    if start_index == -1:
        return text
    end_index = text.find("</think>", start_index)
    if end_index == -1:
        return text
    return text[end_index+len("</think>"):]

#字符串数组或者dict数组转换成markdown的表格字符串输出
def convert_to_markdown_table(items):
    if not items:
        return ""
    if isinstance(items[0], dict):
        headers = items[0].keys()
        rows = [item.values() for item in items]
    else:
        headers = ["value"]
        rows = [[item] for item in items]
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        table += "| " + " | ".join(map(str, row)) + " |\n"
    return table.strip()

#写一个函数,可以计算字符串总字符长度,包含换行符
def get_total_char_length(text):
    return len(text.replace("\n", ""))

def build_yield_response(event, content):
    return {"event": event, f"{event}": content}

#删除字符串数组中单行字符数超过LOG_FETCHER_MAX_LINE_CHAR_LENGTH的行
def filter_long_lines(content_lines:list[str]=[]):
    return [line for line in content_lines if get_total_char_length(line) <= LOG_FETCHER_MAX_LINE_CHAR_LENGTH]

#写一个函数,输入参数为字符串数组,最大支持字符数,开始index,maxlines返回使用的行数
def get_used_lines(content_lines, max_char_length, start_index, maxlines):
    total_char_length = 0
    used_lines = 0
    for line in content_lines[start_index:]:
        line_length = get_total_char_length(line)
        if total_char_length + line_length > max_char_length:
            if line_length > max_char_length:
                used_lines += 1
                break
            break
        total_char_length += line_length
        used_lines += 1
        if used_lines >= maxlines:
            break
    return used_lines

def fetch_json_content(json_str):
    import json5
    import re
    try:
        start_index = json_str.find("```json") + len("```json")
        end_index = json_str.find("```", start_index)
        output = json_str[start_index:end_index].strip()
        try:
            return json5.loads(output)
        except json.JSONDecodeError as e:
            # 尝试第二次：替换单反斜杠为双反斜杠
            fixed = re.sub(r'(?<!\\)\\(?![\\ntbr"\'/u])', r'\\\\', output)
            try:
                return json5.loads(fixed)
            except json5.JSONDecodeError as e:
                print(f"[JSON 解析失败] {e}\n原始内容:\n{output[:300]}...")
                return None
    except Exception as e:
        print(f"Error: Invalid JSON string {e}")
        return None

def delete_files_by_regex(root_dir: str, pattern: str, recursive: bool = True):
    """
    删除 root_dir 目录下所有文件名（不含路径）能被正则表达式 pattern 匹配到的文件。
    同时，把所有未被删除的文件移动到 root_dir 根目录，并删除所有子目录。
    参数:
        root_dir: 起始目录
        pattern: 正则表达式字符串
        recursive: 是否递归子目录，默认 True
    返回:
        已删除文件的绝对路径列表
    """
    deleted_files = []
    regex = re.compile(pattern)

    # 收集所有文件路径
    all_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            all_files.append(full_path)

    # 删除匹配的文件
    for full_path in all_files:
        fname = os.path.basename(full_path)
        if not regex.search(fname):
            try:
                os.remove(full_path)
                deleted_files.append(full_path)
            except Exception as e:
                print(f"[WARN] 删除失败，跳过文件: {full_path} 原因: {e}")

    # 移动未删除的文件到 root_dir 根目录
    for full_path in all_files:
        if full_path in deleted_files:
            continue
        target_path = os.path.join(root_dir, os.path.basename(full_path))
        if os.path.abspath(full_path) != os.path.abspath(target_path):
            try:
                shutil.move(full_path, target_path)
            except Exception as e:
                print(f"[WARN] 移动文件失败，跳过: {full_path} 原因: {e}")

    # 删除所有子目录
    for dirpath, dirnames, _ in os.walk(root_dir, topdown=False):
        for dirname in dirnames:
            dir_full_path = os.path.join(dirpath, dirname)
            try:
                os.rmdir(dir_full_path)
            except Exception as e:
                print(f"[WARN] 删除目录失败，跳过: {dir_full_path} 原因: {e}")

    return deleted_files

def detect_log_file_type(file_path: str) -> str:
    """
    检测整个日志文件是 kernel 打印还是 logcat 打印。
    规则：
    - 如果文件中有 logcat 格式的行，则判定为 logcat 文件。
    - 否则，如果全部是 kernel 打印或混合，但没有 logcat，则判定为 kernel 文件。
    """
    kernel_pattern = re.compile(r'\[\s*\d+\.\d+(?:@\d+)?\]')  # [    1.234567] 或 [    1.234567@2]
    logcat_pattern = re.compile(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(\d+\s+\d+\s+)?[VDIWEF]')

    has_logcat = False
    has_kernel = False

    logcat_count = 0
    kernel_count = 0
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if kernel_pattern.search(line):
                kernel_count += 1
                if kernel_count >= 20:
                    has_kernel = True
                    break
            elif logcat_pattern.match(line):
                    logcat_count += 1
                    if logcat_count >= 20:
                        has_logcat = True
                        break
            #看行内是否包含Hello world, Now in BL33Z
            elif "Hello world, Now in BL33Z" in line:
                has_kernel = True
                break
            

    if has_logcat:
        return "logcat"  # 只要有 logcat，就算 logcat 文件
    elif has_kernel:
        return "kernel"
    else:
        return "unknown"

def convert_file_to_utf8(file_path):
    """
    Check if a file is UTF-16 (LE/BE) or contains null bytes when read as UTF-8,
    and convert it to UTF-8 in place if needed.
    """
    if not os.path.exists(file_path):
        return

    # Detect encoding
    encoding = 'utf-8'
    needs_conversion = False
    
    try:
        # Check for BOM
        with open(file_path, 'rb') as f:
            raw_data = f.read(4)
        
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            encoding = 'utf-16'
            needs_conversion = True
        else:
            # Check for null bytes in first chunk when reading as utf-8
            # (Heuristic for UTF-16 LE without BOM or other binary formats)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    chunk = f.read(4096)
                    if '\0' in chunk:
                         # Likely UTF-16 LE without BOM
                         encoding = 'utf-16'
                         needs_conversion = True
            except Exception:
                pass
    except Exception as e:
        print(f"Error detecting encoding for {file_path}: {e}")
        return

    if needs_conversion:
        print(f"Converting {file_path} from {encoding} to utf-8...")
        try:
            # Read all content with detected encoding
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
            
            # Write back as utf-8
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Conversion successful for {file_path}")
        except Exception as e:
            print(f"Failed to convert {file_path}: {e}")

#写一个函数，通过detect_log_file_type函数判断目录下所有文件的类型，返回logcat和kernel的文件列表
def get_logcat_kernel_file_list(dir_path):
    logcat_file_list = []
    kernel_file_list = []
    #判空
    if not os.path.isdir(dir_path):
        print(f"目录不存在: {dir_path}")
        return logcat_file_list, kernel_file_list
    for file in os.listdir(dir_path):
        file_path = os.path.join(dir_path, file)
        if os.path.isfile(file_path):
            file_type = detect_log_file_type(file_path)
            if file_type == "logcat":
                logcat_file_list.append(file_path)
            elif file_type == "kernel":
                kernel_file_list.append(file_path)
    return logcat_file_list, kernel_file_list
def copy_log_txt_files(src_dir, dst_dir):
    """
    将 src_dir 目录（含子目录）下所有以 .log 或 .txt 结尾的文件
    拷贝到 dst_dir 目录中，保持原文件名。
    若目标目录不存在则自动创建。
    """
    if not os.path.isdir(src_dir):
        raise NotADirectoryError(f"源目录不存在: {src_dir}")

    os.makedirs(dst_dir, exist_ok=True)

    for dirpath, _, filenames in os.walk(src_dir):
        for fname in filenames:
            if fname.lower().endswith(('.log', '.txt')):
                src_file = os.path.join(dirpath, fname)
                dst_file = os.path.join(dst_dir, fname)
                try:
                    # 若目标已存在同名文件，直接覆盖
                    shutil.copy2(src_file, dst_file)
                except Exception as e:
                    # 拷贝失败则打印警告并跳过
                    print(f"[WARN] 拷贝失败，跳过文件: {src_file} 原因: {e}")
def is_cts_result_zip(zip_path: str) -> bool:
    """
    判断压缩包是否是 CTS/GTS 认证结果压缩包。
    方法：逐层扫描压缩包（最多三层），每一层检查是否同时包含 required_files 和 required_dirs。
    """
    required_files = {
        "test_result.xml",
        "test_result.html",
        "test_result_failures_suite.html",
    }
    required_dirs = {
        "module_reports/",
        "report-log-files/",
    }

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_contents = zf.namelist()
            zip_contents = [p.replace("\\", "/").lower() for p in zip_contents]

            # 只考虑三层以内的路径
            zip_contents = [p for p in zip_contents if p.count('/') <= 3]

            # 构建每个目录层级的文件和目录集合
            dir_map = defaultdict(lambda: {"files": set(), "dirs": set()})
            for path in zip_contents:
                parts = path.strip("/").split("/")
                # 当前文件/目录所在的直接父目录
                parent_dir = "/".join(parts[:-1])
                name = parts[-1]
                if path.endswith("/"):  # 目录
                    dir_map[parent_dir]["dirs"].add(name + "/")
                else:  # 文件
                    dir_map[parent_dir]["files"].add(name)

            # 逐层检查每个父目录
            for parent, contents in dir_map.items():
                if required_files.issubset(contents["files"]) and required_dirs.issubset(contents["dirs"]):
                    return True
        return False

    except Exception:
        return False

def extract_archive(file_path, extract_to=None):
    """
    根据文件扩展名自动选择解压缩方式，支持 zip/7z/rar/tar 及其多种压缩格式。
    非压缩格式（log/txt）直接跳过。
    返回解压后的目录路径；若无需解压则返回原文件路径。
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 提取文件扩展名
    ext = os.path.splitext(file_path)[1].lower()
    # 处理 .tar.* 复合扩展名
    if file_path.lower().endswith(('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.lz', '.tar.lzma', '.tar.z')):
        ext = '.tar'

    # 若为非压缩格式，直接返回原路径
    if ext in {'.log', '.txt'}:
        print(f"[INFO] 非压缩格式，跳过解压: {file_path}")
        return file_path

    # 若未指定输出目录，默认解压到当前文件所在目录
    if extract_to is None:
        extract_to = os.path.dirname(file_path)

    print(f"[INFO] 开始解压 {file_path} 到 {extract_to}")

    # 根据扩展名执行解压
    if ext == '.zip':
        with zipfile.ZipFile(file_path, 'r') as zf:
            zf.extractall(extract_to)
        print(f"[INFO] ZIP 解压完成")
    elif ext == '.7z':
        with py7zr.SevenZipFile(file_path, mode='r') as sz:
            sz.extractall(path=extract_to)
        print(f"[INFO] 7Z 解压完成")
    elif ext == '.rar':
        with rarfile.RarFile(file_path) as rf:
            rf.extractall(path=extract_to)
        print(f"[INFO] RAR 解压完成")
    elif ext == '.tar':
        with tarfile.open(file_path, 'r:*') as tf:
            tf.extractall(path=extract_to)
        print(f"[INFO] TAR 解压完成")
    else:
        # 未支持的压缩格式，返回原路径
        print(f"[INFO] 不支持的压缩格式，跳过解压: {file_path}")
        return file_path

    return extract_to

def extract_all_archives(root_dir, extract_to=None, is_extract_all=True, need_recursive=False):
    """
    递归遍历 root_dir 下的所有文件（含子目录），
    对每个文件调用 extract_archive 进行解压。
    若解压成功，则继续对解压出的目录再次递归处理，直到没有可解压文件为止。
    返回已解压的目录路径列表（去重）。
    """
    if not os.path.isdir(root_dir):
        raise NotADirectoryError(f"目录不存在: {root_dir}")

    # 默认解压到原目录
    if extract_to is None:
        extract_to = root_dir
    if is_extract_all:
        copy_log_txt_files(root_dir, extract_to)
    
    extracted_dirs = set()

    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            file_path = os.path.join(dirpath, fname)
            try:
                # todo暂时不处理bugreport文件
                if is_bugreport_zip(file_path):
                    # 若未指定输出目录，默认解压到当前文件所在目录
                    tmp = extract_core_logs_from_bugreport(file_path, extract_to)
                    if not tmp:
                        print(f"[INFO] 从 bugreport 中提取核心日志到 {extract_to} 失败了！")
                    else:
                        print(f"[INFO] 从 bugreport 中提取核心日志到 {extract_to} 成功了！")
                    continue
                if is_cts_result_zip(file_path):
                    continue
                # 尝试解压
                result_path = extract_archive(file_path, extract_to=extract_to)
                # 如果返回的是目录且不是原文件，说明解压成功
                if os.path.isdir(result_path) and result_path != file_path:
                    extracted_dirs.add(os.path.abspath(result_path))
            except Exception as e:
                # 解压失败则跳过，打印日志
                print(f"[WARN] 解压失败，跳过文件: {file_path} 原因: {e}")
    if need_recursive:
        # 对解压出的目录再次递归扫描
        for extracted_dir in list(extracted_dirs):
            sub_dirs = extract_all_archives(extracted_dir, extract_to=extracted_dir)
            extracted_dirs.update(sub_dirs)

    return list(extracted_dirs)

    # 筛选匹配行
def _normalize_line(line: str) -> str:
    """
    将行内容中的十六进制地址、数字、特殊符号去掉，用于去重判断。
    """
    # 去掉十六进制地址（如 0x12345678）
    line = re.sub(r'0x[0-9a-fA-F]+', '', line)
    # 去掉纯数字（如 PID、时间戳等）
    line = re.sub(r'\b\d+\b', '', line)
    # 去掉特殊符号，只保留字母和空格
    line = re.sub(r'[^a-zA-Z\s]', '', line)
    # 合并多余空格
    line = re.sub(r'\s+', ' ', line).strip()
    return line

#系欸个函数，用来判定改行是否是kernel打印

# ✅ 示例用法
# if __name__ == "__main__":
#     result = filter_log_errors(
#         log_path="test.txt",
#         output_dir="tmp/cache/extract"
#     )
#     for line in result:
#         print(line)
#     # _, kernel_files = get_logcat_kernel_file_list("tmp/cache/OTT-84706")
#     # print(kernel_files)





def is_bugreport_zip(file_path: str) -> bool:
    """
    判定一个 zip 文件是否为 Android bugreport 压缩包。
    """
    if not os.path.isfile(file_path):
        return False

    # 1. 文件名判断（常见情况）
    filename = os.path.basename(file_path).lower()
    if filename.startswith("bugreport-") and filename.endswith(".zip"):
        return True

    # 2. 确认是否 zip
    if not zipfile.is_zipfile(file_path):
        return False

    # 3. 查看 ZIP 内部结构（不解压）
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            names = [name.lower() for name in z.namelist()]

            # 特征文件匹配
            patterns = [
                r"^bugreport-.*\.txt$",     # 标准核心文件
                r"dumpstate_board\.txt$",   # 常见 dumpstate 文件
                r"dumpstate_log\.txt$",     # dumpstate 日志
                r"version\.txt$",           # bugreport metadata
            ]

            for name in names:
                for pat in patterns:
                    if re.search(pat, name):
                        return True

    except Exception:
        return False

    return False

#提取bugreport文件中的核心日志，名字
def extract_core_logs_from_bugreport(zip_path: str, output_dir: str):
    """
    从 bugreport-xxx.zip 中提取 bugreport-xxx.txt，并解析其中的关键系统日志和 kernel 日志。
    
    Args:
        zip_path (str): bugreport zip 文件路径
        output_dir (str): 输出目录（自动创建）
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # =============================
        # Step 1：找到 bugreport 主文件
        # =============================
        bugreport_txt = None
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".txt") and "bugreport" in name.lower():
                    bugreport_txt = name
                    break

            if not bugreport_txt:
                raise FileNotFoundError("Zip 中未找到 bugreport-xxx.txt 文件")

                # 读取并写出到目标目录
            output_path = os.path.join(output_dir, os.path.basename(bugreport_txt))
            with zf.open(bugreport_txt) as src, open(output_path, "wb") as dst:
                dst.write(src.read())
    except Exception as e:
        print(f"[ERROR] 从 bugreport zip 提取核心日志失败: {e}")
        return False
    
    return True
    
if __name__ == "__main__":
    # file_path = "hot-start-settings.zip"
    # extract_archive(file_path)
    # print_log_with_box(str(is_bugreport_zip("./tmp/cache/TV-184066/download/Netflix-standby-wakeup-1.zip")))
    # from pprint import pprint
#     json_data_tmp = {'reproduction_steps': '启动设备 -> 播放VOD点播 -> 播放 Skyscraper', 'analysis_direction': '怀疑是音频输出模块存在异常导致电流声及语音缺失', 'suspicious_logs': None, 'irrelevant_files_or_logs': ['duibi-Skyscraper.txt', '其他片源正常.7z'], 'is_certification_related': False, 'main_user_pain_point': 'VOD播放时人物语音缺失影响使用体验', 'one_sentence_summary': 'Skyscraper片源VOD播放出现电流声且无法听到人声', 'summary': '[SWPL-34149][ZTE/Russia][bug#3690/3648][S905X][linux 4.9][Feedback][video]:play vod, there is a current sound output, and the voice of the character cannot be heard', 'description': '[Steps to reproduce]:\r\n1、power on the box\r\n\r\n2.play vod\r\n\r\n3.play\xa0Skyscraper\r\n[Actual results]:\r\nVOD点播播放，出现声音输出有电流声，并且人物说话的声音听不到\r\n[Excepted results]:\r\n声音正常\r\n[Reproducibility rate]: 100%\r\n[Reproduce device]:ZTE/Russia\r\n[SW info]:\r\nZTE-S905X-Linux 4.9\r\n[Compare info]:\xa0\r\n\r\n公板没有linux 4.9多实例播放，无法对比\r\n\r\n*描述*\r\n【白俄&B800V2.0-A高安】【905x】【多实例-最 新版本】盒子起来后，进入到VOD点播播放，出现声音输出有电流声，并且人物说话的声音听不到---AC---复现---文超\r\n【bug onwer】李东升\r\n【复现概率】必现\xa0\r\n【复现环境依赖】外网隧道\r\n【log和片源】B800V2.0_A 多实例异常日志见yichang-Sky.txt；\r\n【对比信息】该片源对比B800V2.0_A单实例同样异常，对比B860H播放正常，B860H正常日志见duibi-Skyscraper.txt。其余片源B800V2.0_A可以正常播放，其他片源日志见 "其他片源正常.7z"\r\n【主线最新版本是否可复现】是\r\n【现象&步骤】盒子起来后，进入到VOD点播播放，播放特定片源Skyscraper', 'comments': ['name: Chumin Zhang\ncreate_date: 2020-09-10T12:58:29.441+0800\ncomment_body: |Topic|Description|\r\n|\xa0*1. Project Info|The project is Linux 4.9 for Belarus.|\r\n|\xa0*2. Customer Due Date|2020.09.18|\r\n|\xa0*3. Issue Serverity|key test|\r\n|\xa0*4. Rejected Times|\xa00|\r\n|\xa0*5. Common Issue？|\xa0yes|\r\n|\xa0*6. Code & Platform & Log Info|20181212\xa0 Linux4.9 SDK|\r\n|\xa07. Reproduce Info|\xa0|\r\n|\xa08.\xa0Additional\xa0Info|\xa0|'], 'files': ['tmp/cache/OTT-13103/extract\\chuankou-zhengchang.txt', 'tmp/cache/OTT-13103/extract\\duibi-Skyscraper.txt', 'tmp/cache/OTT-13103/extract\\logcat-zhengchang.txt', 'tmp/cache/OTT-13103/extract\\Log_2020-09-16Skyscraper_2M.ts播放没声音网口.log', 'tmp/cache/OTT-13103/extract\\Skyscraper_2M.ts播放没声音串口.log', 'tmp/cache/OTT-13103/extract\\vod-chaunkou2.txt', 'tmp/cache/OTT-13103/extract\\yichang-Sky.txt'], 'project': 'P21B8-S905X', 'sdk_version': 'Unassigned'}
#     content = '''
#     ```json
# {
#   "reproduction_steps": "启动设备 -> 播放VOD点播 -> 播放 Skyscraper",
#   "analysis_direction": "音频输出异常（电流声+人声缺失），需分析多实例播放场景下的音视频同步或硬件驱动问题",
#   "suspicious_logs": null,
#   "irrelevant_files_or_logs": [
#     "其他片源正常.7z",
#     "duibi-Skyscraper.txt"
#   ],
#   "is_certification_related": false,
#   "main_user_pain_point": "特定VOD片源播放时音频异常影响观看体验",
#   "one_sentence_summary": "多实例场景下播放Skyscraper片源出现电流声且人声缺失的音视频问题"
# }
# ```
#     '''
#     # print(type(fetch_json_content(content)))
#     pprint(json_data_tmp)

    # result =  filter_log_errors("./tmp/clean_test2.log", "./", None)
    # print(len(result))
    # print(remove_think_content("<think>test需求类问题"))
    result = extract_core_logs_from_bugreport("./test/test.zip", "./test/")
    print(result)



