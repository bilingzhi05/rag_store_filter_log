import os
import sys
import time
import subprocess
import shutil
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlopen
import json

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
# cd /home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log
# cd /home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log && nohup uvicorn main:app --host 0.0.0.0 --port 6666 > uvicorn_main.log 2>&1 &

# curl -# -X POST http://10.68.18.164:6666/filter-log-upload   -F "module_name=audiohal"   -F "file=@/home/amlogic/RAG/clean_log/SWPL-164263_SH-SWPL-164263-ffmpeg_ctc-freeze.log" -o 01271618-audiohal-filter-SWPL-164263.txt

RAG_FILTER_DIR = "/home/bj17300-049u/work/rag_store_filter_log"
WORKSPACE_DIR = "/home/bj17300-049u/work"
LOG_OUTPUT_DIR = "/home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log/log"
CONFIG_MODULE_REGEX_FILE = "/home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log/config_config_module_regex.json"
if RAG_FILTER_DIR not in sys.path:
    sys.path.append(RAG_FILTER_DIR)

from log_cleaner import LogCleaner
from logger import log

app = FastAPI()

class FilterRequest(BaseModel):
    module_name: str
    log_file: str

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

def find_regex_file(module_name: str) -> Optional[str]:
    module_name_lower = module_name.lower()
    preferred_name = "print_regex_patterns_0114.txt"
    fallback_name = "extracted_contents_regex.txt"
    preferred_path = None

    with open(CONFIG_MODULE_REGEX_FILE, "r") as f:
        configs = json.load(f)
    for config in configs:
        if config["module_name"].lower() == module_name_lower:
            preferred_path = config["regex_file_path"]
            break
    log(f"preferred_path: {preferred_path}")
    return preferred_path

def build_combined_regex_file(module_names: list[str]) -> tuple[str, list[str], str]:
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    combined_name = "_".join(module_names)
    combined_path = os.path.join(LOG_OUTPUT_DIR, f"combined_regex_{combined_name}.txt")
    invalid_path = os.path.join(LOG_OUTPUT_DIR, f"invalid_regex_{combined_name}.txt")
    patterns = set()
    for module_name in module_names:
        regex_file = find_regex_file(module_name)
        if not regex_file or not os.path.exists(regex_file):
            log(f"regex file not found for module: {module_name}")
            raise HTTPException(status_code=404, detail=f"regex file not found for module: {module_name}")
        with open(regex_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                pattern = line.strip()
                if pattern:
                    patterns.add(pattern)
    valid_patterns = []
    invalid_patterns = []
    for pattern in sorted(patterns):
        result = subprocess.run(
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
            ["rg", "-i", "-f", regex_file, clean_log_path],
            stdout=out_f,
            stderr=subprocess.PIPE,
            text=True
        )
    duration = time.time() - start_time
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "rg failed")
    return duration

def _save_upload_file(upload: UploadFile) -> str:
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    filename = os.path.basename(upload.filename or "uploaded.log")
    saved_path = os.path.join(LOG_OUTPUT_DIR, f"input_{filename}")
    with open(saved_path, "wb") as out_f:
        shutil.copyfileobj(upload.file, out_f)
    return saved_path

def _process_filter(module_name: str, input_path: str) -> FileResponse:
    input_name = os.path.basename(input_path)
    start_time = time.time()
    clean_path = get_clean_path(input_path)
    log(f"get_clean_path duration: {time.time() - start_time:.2f} seconds")
    module_names = parse_modules(module_name)
    log(f"parse_modules duration: {time.time() - start_time:.2f} seconds")
    if not module_names:
        raise HTTPException(status_code=400, detail="module_name is empty")
    regex_file, invalid_patterns, invalid_path = build_combined_regex_file(module_names)
    log(f"build_combined_regex_file duration: {time.time() - start_time:.2f} seconds")
    if invalid_patterns:
        log(f"invalid patterns count: {len(invalid_patterns)}")
    all_modules = "_".join(module_names)
    output_path = os.path.join(LOG_OUTPUT_DIR, f"filter_{all_modules}_{input_name}")
    log(f"filter_log_with_rg: regex_file={regex_file}, \n clean_path={clean_path}, \n output_path={output_path}")
    duration = filter_log_with_rg(regex_file, clean_path, output_path)
    log(f"filter_log_with_rg duration: {duration:.2f} seconds")
    return FileResponse(output_path, filename=os.path.basename(output_path))

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
    saved_input_path = os.path.join(LOG_OUTPUT_DIR, f"input_{input_name}")
    if input_path != saved_input_path:
        shutil.copy2(input_path, saved_input_path)
    return _process_filter(request.module_name, saved_input_path)

@app.post("/filter-log-upload")
def filter_log_upload(module_name: str = Form(...), file: UploadFile = File(...)):
    log(f"正在接受上传的文件: {file.filename}, 选择的模块是: {module_name}")
    saved_input_path = _save_upload_file(file)
    log(f"上传的文件已保存到: {saved_input_path}")
    return _process_filter(module_name, saved_input_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
