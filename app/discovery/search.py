"""搜索引擎按指纹发现（new-api/one-api 默认页脚、链动小铺 shopApi 等）。需要 BRAVE_API_KEY，未配置时关闭。"""
from .. import config
from ..net import client

QUERIES = ['"Powered by New API"', '"由 New API 驱动"', '"one-api" 中转 令牌', 'catfk.com/shop', 'pay.ldxp.cn/shop']

class SearchEngine:
    id, min_interval_h = "search", 24
    @property
    def enabled(self): return bool(config.BRAVE_API_KEY)
    def discover(self):
        with client(headers={"X-Subscription-Token": config.BRAVE_API_KEY, "Accept": "application/json"}) as c:
            for q in QUERIES:
                r = c.get("https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": 20})
                if r.status_code != 200: continue
                for it in (r.json().get("web") or {}).get("results", []):
                    hint = "card_shop" if "shop" in q else "relay"
                    yield it.get("url"), hint, f"search:{q} {it.get('title', '')}", None
