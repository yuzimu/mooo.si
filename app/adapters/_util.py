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


def page_window(key: str, per_run: int, total_pages: int | None = None):
    """轮转分页：每轮固定抓第 1 页（最新/热门）+ 从游标起 per_run-1 页，多轮后覆盖全部页；游标存 Mongo。"""
    from .. import store
    st = store.db().discovery_state.find_one({"_id": f"pages:{key}"}) or {}
    start = max(2, int(st.get("next") or 2))
    if total_pages and start > total_pages: start = 2
    pages = [1] + list(range(start, start + max(per_run - 1, 0)))
    if total_pages: pages = [x for x in pages if x <= total_pages]
    return pages

def page_advance(key: str, last_page: int, total_pages: int | None, done: bool):
    from .. import store
    nxt = 2 if done or (total_pages and last_page >= total_pages) else last_page + 1
    store.db().discovery_state.update_one({"_id": f"pages:{key}"}, {"$set": {"next": nxt, "total": total_pages, "at": store.now()}}, upsert=True)
