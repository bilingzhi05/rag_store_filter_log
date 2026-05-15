import os
import sys
import time
import subprocess
import shutil
import csv
import re
import zipfile
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlopen
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
# cd /home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log
# cd /home/bj17300-049u/work/rag_store_filter_log && nohup uvicorn fast_api_get_log.main:app --host 0.0.0.0 --port 6666 > uvicorn_main.log 2>&1 &

# curl -# -X POST http://10.68.18.164:6666/filter-log-upload   -F "module_name=audiohal"   -F "file=@/home/amlogic/RAG/clean_log/SWPL-164263_SH-SWPL-164263-ffmpeg_ctc-freeze.log" -o 01271618-audiohal-filter-SWPL-164263.txt

RAG_FILTER_DIR = "/home/amlogic/FAE/AutoLog/lingzhi.bi/extract_module_errlog_and_identitication/rag_store_filter_log"
WORKSPACE_DIR = "/home/amlogic/FAE/AutoLog/lingzhi.bi/extract_module_errlog_and_identitication/code"
LOG_OUTPUT_DIR = "/home/amlogic/FAE/AutoLog/lingzhi.bi/extract_module_errlog_and_identitication/rag_store_filter_log/log"
CONFIG_MODULE_REGEX_FILE = "/home/amlogic/FAE/AutoLog/lingzhi.bi/extract_module_errlog_and_identitication/rag_store_filter_log/fast_api_get_log/config_config_module_regex.json"
if RAG_FILTER_DIR not in sys.path:
    sys.path.append(RAG_FILTER_DIR)

from log_cleaner import LogCleaner
from logger import log

app = FastAPI()

class FilterRequest(BaseModel):
    module_name: str
    log_file: str


def normalize_module_key(value: str) -> str:
    """
    将模块名归一化为“去掉特殊符号 + 小写”的 key，用于匹配配置项。
    规则：
    - 转小写
    - 去掉所有非字母数字字符（例如 '-' '_' 空格 '.' '/' 等）
    示例：
    - 'audio-hal' -> 'audiohal'
    - 'Audio_Hal' -> 'audiohal'
    - 'audio.hal' -> 'audiohal'
    """
    s = (value or "").strip().lower()
    return "".join(ch for ch in s if ch.isalnum())

def get_clean_path(log_file_path: str) -> str:
    if not os.path.exists(log_file_path):
        raise FileNotFoundError(f"log file not found: {log_file_path}")
    cleaner = LogCleaner(log_file_path)
    clean_file_path, _ = cleaner.clean_log()
    if not clean_file_path or not os.path.exists(clean_file_path):
        raise FileNotFoundError(f"clean file not found: {clean_file_path}")
    return clean_file_path

def resolve_input_log(log_file: str) -> str:
    if os.path.exists(log_file):
        return log_file
    parsed = urlparse(log_file)
    if parsed.scheme in ("http", "https"):
        os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
        file_name = os.path.basename(parsed.path) or "downloaded.log"
        local_path = os.path.join(LOG_OUTPUT_DIR, file_name)
        with urlopen(log_file) as response, open(local_path, "wb") as out_f:
            shutil.copyfileobj(response, out_f)
        return local_path
    raise FileNotFoundError(f"log file not found: {log_file}")

def parse_modules(module_name: str) -> list[str]:
    parts = set([item.strip() for item in module_name.split(",")])
    return [item for item in parts if item]

def find_latest_logset(module_name: str) -> Optional[str]:
    module_name_lower = module_name.lower()
    wrapper_candidates = []
    for name in os.listdir(WORKSPACE_DIR):
        name_lower = name.lower()
        if name_lower == f"{module_name_lower}_wraper" or name_lower == f"{module_name_lower}_wrapper":
            wrapper_candidates.append(os.path.join(WORKSPACE_DIR, name_lower))
    logset_candidates = []
    log(f"wrapper_candidates: {wrapper_candidates}")
    for wrapper_dir in wrapper_candidates:
        for root, dirs, _ in os.walk(wrapper_dir):
            for d in dirs:
                if d.lower() == f"{module_name_lower}_logset":
                    logset_candidates.append(os.path.join(root, d))
    if not logset_candidates:
        return None
    return max(logset_candidates, key=os.path.getmtime)

def find_regex_file(module_name: str) -> tuple[Optional[str], list[str]]:
    module_key = normalize_module_key(module_name)
    preferred_name = "print_regex_patterns_0114.txt"
    fallback_name = "extracted_contents_regex.txt"
    preferred_path = None

    existing_module_names = []
    with open(CONFIG_MODULE_REGEX_FILE, "r") as f:
        configs = json.load(f)
    for config in configs:
        existing_module_names.append(config.get("module_name", ""))
        if normalize_module_key(config.get("module_name", "")) == module_key:
            preferred_path = config["regex_file_path"]
            break
    log(f"preferred_path: {preferred_path}")
    return preferred_path, existing_module_names

def build_combined_regex_file(module_names: list[str]) -> tuple[str, list[str], str]:
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    combined_name = "_".join(module_names)
    combined_path = os.path.join(LOG_OUTPUT_DIR, f"combined_regex_{combined_name}.txt")
    invalid_path = os.path.join(LOG_OUTPUT_DIR, f"invalid_regex_{combined_name}.txt")
    patterns = set()
    for module_name in module_names:
        regex_file, existing_module_names = find_regex_file(module_name)
        if not regex_file or not os.path.exists(regex_file):
            log(f"regex file not found for module: {module_name}")
            raise HTTPException(status_code=404, detail=f"regex file not found for module: {module_name}，有这些模块名: {existing_module_names}")
        with open(regex_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                pattern = line.strip()
                if pattern:
                    patterns.add(pattern)
    valid_patterns = []
    invalid_patterns = []
    for pattern in sorted(patterns):
        result = subprocess.run(
            # 需要使用rg 14.0.0版本以上
            ["rg", "--pcre2", "-n", "-e", pattern, "/dev/null"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 2:
            invalid_patterns.append(pattern)
        else:
            valid_patterns.append(pattern)
    with open(combined_path, "w", encoding="utf-8") as out_f:
        for pattern in valid_patterns:
            out_f.write(pattern + "\n")
    if invalid_patterns:
        with open(invalid_path, "w", encoding="utf-8") as out_f:
            for pattern in invalid_patterns:
                out_f.write(pattern + "\n")
        log(f"invalid regex patterns saved to: {invalid_path}")
    return combined_path, invalid_patterns, invalid_path

def filter_log_with_rg(regex_file: str, clean_log_path: str, output_path: str) -> float:
    start_time = time.time()
    with open(output_path, "w", encoding="utf-8") as out_f:
        result = subprocess.run(
            # 需要使用rg 14.0.0版本以上
            ["rg", "-f", regex_file, clean_log_path],
            stdout=out_f,
            stderr=subprocess.PIPE,
            text=True
        )
    duration = time.time() - start_time
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "rg failed")
    return duration

def _parse_clean_line(line: str) -> tuple[Optional[int], str]:
    s = (line or "").rstrip("\n")
    m = re.match(r"^\s*(\d+):\s*(.*)$", s)
    if m:
        s = m.group(2)
    m = re.match(r"^\s*Line\s+(\d+)\s*:\s*(.*)$", s)
    if m:
        return int(m.group(1)), m.group(2)
    return None, s

def write_filtered_log_pattern_csv(
    regex_file: str,
    filtered_log_path: str,
    output_csv_path: str,
    max_patterns_per_line: int = 1
) -> dict:
    patterns: list[str] = []
    with open(regex_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            p = raw.strip()
            if p:
                patterns.append(p)

    compiled: list[tuple[str, re.Pattern]] = []
    invalid_patterns: list[str] = []
    for p in patterns:
        try:
            compiled.append((p, re.compile(p, re.IGNORECASE)))
        except re.error:
            invalid_patterns.append(p)

    rows_written = 0
    lines_total = 0
    lines_with_match = 0

    with open(filtered_log_path, "r", encoding="utf-8", errors="ignore") as in_f, open(output_csv_path, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=["line_no", "log", "regex"], delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writeheader()
        for raw_line in in_f:
            lines_total += 1
            line_no, log_text = _parse_clean_line(raw_line)
            matched = 0
            for pattern_text, pattern_re in compiled:
                if pattern_re.search(log_text):
                    writer.writerow(
                        {"line_no": line_no if line_no is not None else "", "log": log_text, "regex": pattern_text}
                    )
                    rows_written += 1
                    matched += 1
                    if matched >= max_patterns_per_line:
                        break
            if matched == 0:
                writer.writerow({"line_no": line_no if line_no is not None else "", "log": log_text, "regex": ""})
                rows_written += 1
            else:
                lines_with_match += 1

    return {
        "lines_total": lines_total,
        "lines_with_match": lines_with_match,
        "rows_written": rows_written,
        "python_re_invalid_patterns_count": len(invalid_patterns),
    }

def _save_upload_file(upload: UploadFile, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(upload.filename or "uploaded.log")
    saved_path = os.path.join(output_dir, f"input_{filename}")
    with open(saved_path, "wb") as out_f:
        shutil.copyfileobj(upload.file, out_f)
    return saved_path

def _process_filter(module_name: str, input_path: str, output_dir: str) -> FileResponse:
    input_name = os.path.basename(input_path)
    start_time = time.time()
    module_names = parse_modules(module_name)
    log(f"parse_modules duration: {time.time() - start_time:.2f} seconds")
    if not module_names:
        raise HTTPException(status_code=400, detail="module_name is empty")
    regex_file, invalid_patterns, invalid_path = build_combined_regex_file(module_names)
    log(f"build_combined_regex_file duration: {time.time() - start_time:.2f} seconds")
    if invalid_patterns:
        log(f"invalid patterns count: {len(invalid_patterns)}")
    clean_path = get_clean_path(input_path)
    log(f"get_clean_path duration: {time.time() - start_time:.2f} seconds")
    all_modules = "_".join(module_names)
    
    output_path = os.path.join(output_dir, f"filter_{all_modules}_{input_name}")
    log(f"filter_log_with_rg: regex_file={regex_file}, \n clean_path={clean_path}, \n output_path={output_path}")
    duration = filter_log_with_rg(regex_file, clean_path, output_path)
    log(f"filter_log_with_rg duration: {duration:.2f} seconds")
    csv_path = output_path + ".csv"
    mapping_stats = write_filtered_log_pattern_csv(
        regex_file=regex_file,
        filtered_log_path=output_path,
        output_csv_path=csv_path,
        max_patterns_per_line=1
    )
    log(f"pattern mapping csv saved: {csv_path}, stats={mapping_stats}")
    zip_name = f"result_{all_modules}_{os.path.basename(clean_path)}.zip"
    zip_path = os.path.join(output_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(output_path, arcname=os.path.basename(output_path))
        zf.write(clean_path, arcname=os.path.basename(clean_path))
    return FileResponse(zip_path, filename=os.path.basename(zip_path))

@app.get("/invalid-regex")
def invalid_regex(module_name: str):
    module_names = parse_modules(module_name)
    if not module_names:
        raise HTTPException(status_code=400, detail="module_name is empty")
    _, invalid_patterns, invalid_path = build_combined_regex_file(module_names)
    return {"invalid_count": len(invalid_patterns), "invalid_path": invalid_path, "invalid_patterns": invalid_patterns}

@app.post("/filter-log")
def filter_log(request: FilterRequest):
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    input_path = resolve_input_log(request.log_file)
    input_name = os.path.basename(input_path)
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d')
    output_dir = os.path.join(LOG_OUTPUT_DIR, timestamp, request.module_name)
    os.makedirs(output_dir, exist_ok=True)
    saved_input_path = os.path.join(output_dir, f"input_{input_name}")
    if input_path != saved_input_path:
        shutil.copy2(input_path, saved_input_path)
    return _process_filter(request.module_name, saved_input_path, output_dir)

@app.post("/filter-log-upload")
def filter_log_upload(module_name: str = Form(...), file: UploadFile = File(...)):
    log(f"正在接受上传的文件: {file.filename}, 选择的模块是: {module_name}")
    module_names = parse_modules(module_name)
    if not module_names:
        raise HTTPException(status_code=400, detail="module_name is empty")
    for module in module_names:
        regex_file, existing_module_names = find_regex_file(module)
        if not regex_file or not os.path.exists(regex_file):
            raise HTTPException(status_code=404, detail=f"regex file not found for module: {module}，数据库保存的模块名有: {existing_module_names}")
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d')
    output_dir = os.path.join(LOG_OUTPUT_DIR, timestamp, module_name)
    os.makedirs(output_dir, exist_ok=True)
    saved_input_path = _save_upload_file(file, output_dir)
    log(f"上传的文件已保存到: {saved_input_path}")
    return _process_filter(module_name, saved_input_path, output_dir)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
