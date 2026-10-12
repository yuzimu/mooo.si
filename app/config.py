import os
MONGO_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017/")   # 测试可用 mongomock://
MONGO_DB = os.getenv("MONGO_DB", "mooo")
RAW_RETENTION_DAYS = int(os.getenv("RAW_RETENTION_DAYS", "14"))
PROXY_POOL_URL = os.getenv("PROXY_POOL_URL", "")      # 返回代理列表的 URL（每行一个）
PROXY_LIST = [p for p in os.getenv("PROXY_LIST", "").split(",") if p]
BROWSER_CDP_URL = os.getenv("BROWSER_CDP_URL", "")    # 指纹浏览器 CDP 端点 ws://... 或 http://...
CRAWL_INTERVAL_MIN = int(os.getenv("CRAWL_INTERVAL_MIN", "30"))
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "1") == "1"
USER_AGENT = "mooo.si-aggregator/0.2 (+https://mooo.si)"
BROWSER_UA = os.getenv("BROWSER_UA", "Mozilla/5.0 (compatible; mooo.si-aggregator/0.3; +https://mooo.si)")
ENABLED_ADAPTERS = [a for a in os.getenv("ENABLED_ADAPTERS", "").split(",") if a]  # 空=按各适配器默认
CRAWL_PAGE_DELAY = float(os.getenv("CRAWL_PAGE_DELAY", "1.5"))
AIGOOD_PAGES = int(os.getenv("AIGOOD_PAGES", "5"))
APINAV_SITE_PAGES = int(os.getenv("APINAV_SITE_PAGES", "7"))
APINAV_CARD_PAGES = int(os.getenv("APINAV_CARD_PAGES", "6"))
LDXP_SHOWCASE_PAGES = int(os.getenv("LDXP_SHOWCASE_PAGES", "10"))
OAI9_HOT_URL = os.getenv("OAI9_HOT_URL", "")
LDXP_MERCHANT_TOKEN = os.getenv("LDXP_MERCHANT_TOKEN", "")
LDXP_MERCHANT_KEYWORDS = [k for k in os.getenv("LDXP_MERCHANT_KEYWORDS", "gemini,claude,plus,gcp").split(",") if k]
GROUPS_PER_PAGE = int(os.getenv("GROUPS_PER_PAGE", "12"))
