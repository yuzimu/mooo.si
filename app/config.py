import os
MONGO_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017/")   # 测试可用 mongomock://
MONGO_DB = os.getenv("MONGO_DB", "mooo")
RAW_RETENTION_DAYS = int(os.getenv("RAW_RETENTION_DAYS", "7"))
RAW_MAX_BYTES = int(os.getenv("RAW_MAX_BYTES", str(1024 * 1024)))
PROXY_POOL_URL = os.getenv("PROXY_POOL_URL", "")      # 返回代理列表的 URL（每行一个）
PROXY_LIST = [p for p in os.getenv("PROXY_LIST", "").split(",") if p]
BROWSER_CDP_URL = os.getenv("BROWSER_CDP_URL", "")    # 指纹浏览器 CDP 端点 ws://... 或 http://...
CRAWL_INTERVAL_MIN = int(os.getenv("CRAWL_INTERVAL_MIN", "30"))
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "1") == "1"
USER_AGENT = "mooo.si-aggregator/0.2 (+https://mooo.si)"
BROWSER_UA = os.getenv("BROWSER_UA", "Mozilla/5.0 (compatible; mooo.si-aggregator/0.3; +https://mooo.si)")
ENABLED_ADAPTERS = [a for a in os.getenv("ENABLED_ADAPTERS", "").split(",") if a]  # 空=按各适配器默认
CRAWL_PAGE_DELAY = float(os.getenv("CRAWL_PAGE_DELAY", "1.5"))
AIGOOD_PAGES = int(os.getenv("AIGOOD_PAGES", "20"))
APINAV_SITE_PAGES = int(os.getenv("APINAV_SITE_PAGES", "7"))
APINAV_CARD_PAGES = int(os.getenv("APINAV_CARD_PAGES", "40"))
LDXP_SHOWCASE_PAGES = int(os.getenv("LDXP_SHOWCASE_PAGES", "130"))
OAI9_HOT_URL = os.getenv("OAI9_HOT_URL", "")
LDXP_MERCHANT_TOKEN = os.getenv("LDXP_MERCHANT_TOKEN", "")
LDXP_MERCHANT_KEYWORDS = [k for k in os.getenv("LDXP_MERCHANT_KEYWORDS", "gemini,claude,plus,gcp").split(",") if k]
# 链动小铺 ShopApi 请求头：UA 留空则用 USER_AGENT（实测 ESA 只拦 httpx 库默认 UA）。
# LDXP_UA=Baiduspider / LDXP_X_REAL_IP=... 可按需覆盖；实测 X-Real-IP 对放行与否无影响。
LDXP_UA = os.getenv("LDXP_UA", "")
LDXP_X_REAL_IP = os.getenv("LDXP_X_REAL_IP", "")
GROUPS_PER_PAGE = int(os.getenv("GROUPS_PER_PAGE", "12"))
TG_DB_PATH = os.getenv("TG_DB_PATH", "")            # 只读挂载的 tg-collector messages.db
TG_PREVIEW_MAX = int(os.getenv("TG_PREVIEW_MAX", "40"))
GITHUB_LIST_URLS = [u for u in os.getenv("GITHUB_LIST_URLS",
    "https://raw.githubusercontent.com/LiLittleCat/awesome-free-chatgpt/main/README.md").split(",") if u]
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "4"))         # Asia/Shanghai
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", "0"))
TZ = os.getenv("TZ_NAME", "Asia/Shanghai")
TARGET_CRAWL_MAX = int(os.getenv("TARGET_CRAWL_MAX", "300"))   # 每轮最多目标数
TARGET_WORKERS = int(os.getenv("TARGET_WORKERS", "4"))   # 全局并发上限；同域名串行
DOMAIN_DELAY = float(os.getenv("DOMAIN_DELAY", "2.0"))
RELAY_FEATURED = os.getenv("RELAY_FEATURED", r"gpt-5|gpt-4o|o3|claude|gemini|grok|deepseek|nano-banana|image|veo|sora")
PROXY_REQUIRED = os.getenv("PROXY_REQUIRED", "0") == "1"   # 生产=1：无代理则不抓
CRAWL_EVERY_HOURS = int(os.getenv("CRAWL_EVERY_HOURS", "24"))
MAX_PAGES_PER_TARGET = int(os.getenv("MAX_PAGES_PER_TARGET", "5"))
TARGET_MIN_INTERVAL_H = float(os.getenv("TARGET_MIN_INTERVAL_H", "6"))   # 同一目标两次抓取最小间隔
SITE_URL = os.getenv("SITE_URL", "https://mooo.si").rstrip("/")
OFFER_TTL_H = float(os.getenv("OFFER_TTL_H", "48"))   # 轮转分页来源报价多久未再出现即过期
CYCLE_BYTE_BUDGET_MB = float(os.getenv("CYCLE_BYTE_BUDGET_MB", "150"))   # 单轮定向抓取流量上限，超出则剩余目标顺延
FAIL_RETRY_H = float(os.getenv("FAIL_RETRY_H", "12"))   # 失败（非验证码）目标重试间隔

LINK_PROBE_TTL_H = float(os.getenv("LINK_PROBE_TTL_H", "24"))
LINK_PROBE_PER_CYCLE = int(os.getenv("LINK_PROBE_PER_CYCLE", "60"))

# 每轮定向抓取的时间预算（分钟），需小于 CRAWL_EVERY_HOURS，未完成目标下一轮续跑
CYCLE_MAX_MINUTES = int(os.getenv("CYCLE_MAX_MINUTES", "0"))  # 0 = 不限，跑完为止
