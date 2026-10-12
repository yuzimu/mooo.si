import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/mooo.db")
PROXY_POOL_URL = os.getenv("PROXY_POOL_URL", "")      # 返回代理列表的 URL（每行一个）
PROXY_LIST = [p for p in os.getenv("PROXY_LIST", "").split(",") if p]
BROWSER_CDP_URL = os.getenv("BROWSER_CDP_URL", "")    # 指纹浏览器 CDP 端点 ws://... 或 http://...
CRAWL_INTERVAL_MIN = int(os.getenv("CRAWL_INTERVAL_MIN", "30"))
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "1") == "1"
USER_AGENT = "mooo.si-aggregator/0.2 (+https://mooo.si)"
