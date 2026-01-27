# rag_store_filter_log
rag_store_filter_log

需要在父目录创建 store_log_data 存放log 和 db

# 使用 fast_api_get_log 方法

先使用 https://github.com/bilingzhi05/print_code_extract2 项目提取打印代码，
准备好后再启动本项目，配置：
/home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log/config_config_module_regex.json 文件
main.py中修改
RAG_FILTER_DIR = "/home/bj17300-049u/work/rag_store_filter_log"
WORKSPACE_DIR = "/home/bj17300-049u/work" #代码位置
LOG_OUTPUT_DIR = "/home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log/log" #log存放位置
CONFIG_MODULE_REGEX_FILE = "/home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log/config_config_module_regex.json" #模块和正则表位置

启动命令：
cd /home/bj17300-049u/work/rag_store_filter_log/fast_api_get_log && nohup uvicorn main:app --host 0.0.0.0 --port 6666 > uvicorn_main.log 2>&1 &
