import json, re, time
from .. import config

def polite_sleep():
    time.sleep(config.CRAWL_PAGE_DELAY)

def nuxt_payload(html: str):
    """解析 Nuxt 3 `__NUXT_DATA__`（devalue 扁平数组格式）为普通对象。"""
    m = re.search(r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m: raise ValueError("no __NUXT_DATA__")
    a = json.loads(m.group(1)); memo = {}
    wrappers = {"ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef"}
    def r(i):
        if not isinstance(i, int) or i < 0: return None
        if i in memo: return memo[i]
        v = a[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in wrappers: out = r(v[1]) if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in ("Date", "BigInt"): out = v[1]
            elif v and isinstance(v[0], str) and v[0] == "Set": out = [r(x) for x in v[1:]]
            else: out = [r(x) for x in v]
        elif isinstance(v, dict): out = {k: r(x) for k, x in v.items()}
        else: out = v
        memo[i] = out
        return out
    return r(0)

PRICE_RE = re.compile(r"(CNY|USD|USDT|¥|￥|\$)\s*([0-9]+(?:\.[0-9]+)?)")
def parse_price(text):
    m = PRICE_RE.search(text or "")
    if not m: return None, None
    cur = {"¥": "CNY", "￥": "CNY", "$": "USD"}.get(m.group(1), m.group(1))
    return float(m.group(2)), cur
