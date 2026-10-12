"""报价质量：垃圾过滤、分类、链接探活、下架检测。"""
import re
from datetime import timedelta
from urllib.parse import urlsplit
from . import config, store
from .net import client

# —— 垃圾：教程/须知/公告/测试/占位 ——
JUNK_TITLE = re.compile(
    r"(教程|须知|必看|说明(?!书)|公告|通知|温馨提示|售后须知|使用说明|下单前|请先看|看完再买|"
    r"测试商品|测一测|勿拍|不要拍|仅测试|占位|示例|demo\b|sample\b|"
    r"充值教程|开通教程|绑定教程|如何使用|怎么用)", re.I)
JUNK_ZERO = re.compile(r"(免费领取|0元购|零元|面议|联系客服询价)", re.I)

def is_junk(o: dict) -> str | None:
    """返回 junk 原因；None 表示保留。"""
    title = (o.get("title") or "") + " " + (o.get("product") or "")
    if JUNK_TITLE.search(title): return "教程/须知/公告/测试类非商品"
    price = o.get("price")
    if price is not None and price <= 0 and not JUNK_ZERO.search(title):
        return "价格≤0 占位"
    if price is not None and price <= 0 and JUNK_ZERO.search(title):
        return "免费领取/面议占位"
    # 明确标注「勿拍」的说明贴
    if re.search(r"勿拍|不要拍|仅展示|不发货", title): return "明示勿拍/仅展示"
    return None

# —— 分类：有序规则 + 否定词；产品形态优先于品牌 ——
# (category, positive_re, negative_re_or_None)
# 子类写入 tags: 成品号/代充/家庭位/API/接码/邮箱
SUB_RULES = [
    ("家庭位", re.compile(r"家庭[组位]|family\s*slot|车位|拼车|共享位", re.I)),
    ("代充", re.compile(r"代充|直充|官方充|cdk|卡密充|续费|订阅充|官方渠道.*充", re.I)),
    ("成品号", re.compile(r"成品号|独享号|成品\b|账密|带2fa|已接马.*号|白号|普号", re.I)),
    ("接码", re.compile(r"接码|接马|sms|验证码|实卡|手机号验证", re.I)),
    ("邮箱", re.compile(r"邮箱|gmail|outlook|hotmail|icloud|edu\.|edu邮箱", re.I)),
    ("API", re.compile(r"\bapi\b|中转|按量|额度|token|1m\s*token", re.I)),
]

CAT_RULES = [
    # 更具体的在前
    ("gcp-trial", re.compile(r"gcp|google\s*cloud|云试用", re.I), re.compile(r"教程|须知", re.I)),
    ("nano-banana-api", re.compile(r"nano\s*banana|香蕉.*生图|生图\s*api|gpt-image|dall-?e|flux\b|seedream|imagen|midjourney", re.I), None),
    ("adobe-firefly", re.compile(r"firefly|adobe\s*firefly", re.I), re.compile(r"教程", re.I)),
    ("leonardo", re.compile(r"leonardo", re.I), re.compile(r"教程", re.I)),
    ("verify", re.compile(r"接码|接马|kyc|实卡|短信验证|手机号验证|验证码收", re.I),
     re.compile(r"成品号|代充|订阅", re.I)),
    ("email", re.compile(r"(?<![a-z])(gmail|outlook|hotmail|icloud|edu\.?邮箱|教育邮箱|邮箱母号|邮箱账号|邮箱\b)", re.I),
     re.compile(r"接码|接马|成品号.*plus|plus.*成品|代充|订阅", re.I)),
    ("payment", re.compile(r"虚拟卡|礼品卡|visa\b|mastercard|paypal\s*卡|itunes", re.I),
     re.compile(r"接码|接马|成品", re.I)),
    ("api-relay", re.compile(r"中转|按量付费|api\s*额度|额度卡|token\s*额度|\bapi\b.*站|1m\s*token", re.I),
     re.compile(r"成品号|代充|接码|邮箱", re.I)),
    ("gemini", re.compile(r"gemini|google\s*ai|antigravity|反重力|ai\s*ultra", re.I),
     re.compile(r"教程|须知|api\s*中转", re.I)),
    ("grok", re.compile(r"\bgrok\b|supergro|xai\b", re.I), re.compile(r"教程|须知", re.I)),
    ("claude", re.compile(r"claude|anthropic", re.I), re.compile(r"教程|须知|cursor", re.I)),
    ("chatgpt", re.compile(r"chatgpt|chat\s*gpt|\bgpt\b|codex|openai|plus\b|pro\s*x?\d|team\b|business", re.I),
     re.compile(r"教程|须知|claude|gemini|grok|cursor|kiro|gpt-image|dall-?e", re.I)),
    ("ai-tool", re.compile(r"cursor|kiro|perplexity|suno|dreamina|即梦|muse\s*ai|midjourney|windsurf|devin", re.I),
     re.compile(r"教程|须知", re.I)),
    ("social", re.compile(r"telegram|tg\s*premium|推特|twitter|x\s*premium|apple\s*id|多邻国|duolingo|reddit|discord|tiktok", re.I),
     re.compile(r"教程", re.I)),
]

def guess_category(text: str) -> str:
    t = text or ""
    for cat, pos, neg in CAT_RULES:
        if pos.search(t) and not (neg and neg.search(t)):
            return cat
    return "other"

def guess_subtypes(text: str) -> list[str]:
    t = text or ""
    return [name for name, rx in SUB_RULES if rx.search(t)]

# —— 下架 / 空白页 文本特征 ——
OFF_SHELF = re.compile(
    r"商品未上架|商品已下架|已下架|商品不存在|不存在或已|商品已删除|商品已售罄|"
    r"goods\s*not\s*found|item\s*not\s*found|404\s*not\s*found|"
    r"该商品不存在|下架或删除|无法找到该商品|商品已失效|已售罄且下架|"
    r"如有疑问请联系商家", re.I)
CAPTCHA = re.compile(r"aliyun_waf|captcha|challenge-platform|cf-browser-verification|just a moment", re.I)

def classify_page(status: int, text: str, title: str = "") -> str:
    blob = (title or "") + "\n" + (text or "")[:8000]
    if status >= 400: return f"http_{status}"
    if CAPTCHA.search(blob): return "captcha"
    if OFF_SHELF.search(blob): return "off_shelf"
    # SPA 空壳：可见文本极少
    visible = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>|\s+", " ", blob)
    if len(visible.strip()) < 40 and ("id=\"app\"" in (text or "") or "id=\"root\"" in (text or "") or "<!doctype" in (text or "").lower()): return "spa_empty"
    return "ok"

def apply_junk_and_category(batch_limit=50000):
    """对已入库报价重算 junk/category；返回统计。"""
    from .schema import guess_category as _  # noqa — 由本模块覆盖
    d = store.db(); n_junk = n_cat = 0
    for o in d.offers.find({"ignored": {"$ne": True}}, {"title": 1, "product": 1, "price": 1, "category": 1, "tags": 1}).limit(batch_limit):
        text = f'{o.get("product") or ""} {o.get("title") or ""}'
        upd = {}
        reason = is_junk(o)
        if reason:
            upd.update(junk=True, junk_reason=reason)
            n_junk += 1
        else:
            if o.get("junk"): upd["junk"] = False
        cat = guess_category(text)
        subs = guess_subtypes(text)
        if cat != o.get("category"):
            upd["category"] = cat; n_cat += 1
        tags = list(dict.fromkeys([*(o.get("tags") or []), *subs]))
        if tags != (o.get("tags") or []): upd["tags"] = tags
        if upd: d.offers.update_one({"_id": o["_id"]}, {"$set": upd})
    return {"junk_marked": n_junk, "recategorized": n_cat}

def hide_no_url():
    """无商品深链的报价标记 no_url（前台隐藏）。ApiNav 部分卡片只有店铺首页。"""
    r = store.db().offers.update_many(
        {"$or": [{"url": None}, {"url": ""}], "no_url": {"$ne": True}},
        {"$set": {"no_url": True, "link_status": "no_url"}})
    return r.modified_count

def hide_out_of_stock_aggregators():
    """聚合源明示缺货的直接隐藏，无需探活。"""
    r = store.db().offers.update_many(
        {"source": {"$in": ["aigood", "apinav", "ldxp-showcase", "priceai"]}, "in_stock": False,
         "off_shelf": {"$ne": True}},
        {"$set": {"off_shelf": True, "link_status": "aggregator_oos", "off_shelf_at": store.now()}})
    return r.modified_count

def probe_links(limit=80, workers=3, delay=1.2):
    """经代理探活报价链接；标记 off_shelf / captcha / ok。限流。"""
    import time, logging
    from concurrent.futures import ThreadPoolExecutor
    log = logging.getLogger("mooo.quality")
    d = store.db()
    # 优先：近期未探过、有 URL、非 junk、来自卡网商品源
    fresh = store.now() - timedelta(hours=config.LINK_PROBE_TTL_H)
    cand = list(d.offers.find({
        "url": {"$type": "string", "$ne": ""},
        "junk": {"$ne": True}, "ignored": {"$ne": True},
        "source": {"$in": ["aigood", "apinav", "ldxp-showcase", "priceai", "catfk"]},
        "$or": [{"link_checked_at": {"$exists": False}}, {"link_checked_at": {"$lt": fresh}}],
    }, {"url": 1, "title": 1}).sort("fetched_at", -1).limit(limit))
    last = {}
    def one(o):
        u = o["url"]; h = urlsplit(u).hostname or ""
        wait = last.get(h, 0) + delay - time.time()
        if wait > 0: time.sleep(wait)
        last[h] = time.time()
        try:
            with client(headers={"User-Agent": config.BROWSER_UA}) as c:
                try:
                    r = c.head(u, follow_redirects=True, timeout=15)
                    if r.status_code >= 400 or r.status_code in (405, 403) or "text/html" in (r.headers.get("content-type") or ""):
                        r = c.get(u, follow_redirects=True, timeout=20)
                except Exception:
                    r = c.get(u, follow_redirects=True, timeout=20)
            title_m = re.search(r"<title[^>]*>(.*?)</title>", r.text[:50000], re.S | re.I)
            title = (title_m.group(1).strip() if title_m else "")[:120]
            v = classify_page(r.status_code, r.text, title)
            upd = {"link_status": v, "link_checked_at": store.now(), "link_final": str(r.url)[:200]}
            if v == "off_shelf" or v.startswith("http_4"):
                upd.update(off_shelf=True, off_shelf_at=store.now())
            elif v == "ok":
                upd["off_shelf"] = False
            d.offers.update_one({"_id": o["_id"]}, {"$set": upd})
            return v
        except Exception as e:  # noqa: BLE001
            d.offers.update_one({"_id": o["_id"]}, {"$set": {"link_status": "error", "link_error": repr(e)[:200],
                                                              "link_checked_at": store.now()}})
            return "error"
    stats = {}
    with ThreadPoolExecutor(workers) as ex:
        for v in ex.map(one, cand):
            stats[v] = stats.get(v, 0) + 1
    log.info("probe %s of %s: %s", sum(stats.values()), limit, stats)
    return {"probed": sum(stats.values()), "stats": stats}
