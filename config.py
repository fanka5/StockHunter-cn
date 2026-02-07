# config.py
import os
import multiprocessing
from pathlib import Path
from dotenv import load_dotenv

# ===========================
# 1. 环境初始化
# ===========================
# 加载 .env 文件中的环境变量
load_dotenv()

# ===========================
# 2. 路径配置
# ===========================
# 获取当前文件(config.py)所在的目录作为项目根目录
BASE_DIR = Path(__file__).parent

# 数据存储目录
DATA_DIR = BASE_DIR / "data" / "daily"
OUTPUT_DIR = BASE_DIR / "output"

# 自选股文件路径
WATCHLIST_FILE = BASE_DIR / "watchlist.json"

# 自动创建必要的目录
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===========================
# 3. LLM (大模型) 配置
# ===========================
# 优先从环境变量获取，如果没有配置，则使用默认值
LLM_API_KEY = os.getenv("LLM_API_KEY")

# 默认使用硅基流动 (SiliconFlow) 的 API 地址，兼容 OpenAI 格式
# 如果使用 OpenAI，可以在 .env 中改为 https://api.openai.com/v1/chat/completions
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")

# 默认模型 (例如 DeepSeek-V3)，可在 .env 中覆盖
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")

# ===========================
# 4. 网络与代理配置
# ===========================
# 如果 .env 里没配 PROXY_URL，默认为 None (不使用代理)
# 格式示例: http://127.0.0.1:7890
PROXY_URL = os.getenv("PROXY_URL", None)

# ===========================
# 5. 业务参数配置
# ===========================

# --- 下载设置 (Downloader) ---
DEFAULT_START_DATE = "2023-01-01"
DATA_READY_HOUR = 17       # 下午5点后才认为有当日收盘数据
MAX_ATTEMPTS = 7           # 下载最大重试轮次
ABORT_THRESHOLD = 50       # 连续失败多少次停止下载

# --- 性能设置 (Performance) ---
# 动态计算进程数：保留 2 个核心给系统和 UI，其余用于计算
PROCESS_COUNT = max(2, multiprocessing.cpu_count() - 2)

# --- AI 分析设置 (Analyzer) ---
AI_BATCH_SIZE = 10          # 批处理大小
AI_MAX_THREADS = 3          # AI 请求并发数
MAX_STOCKS_TO_ANALYZE = 10  # 非自选股分析数量限制
