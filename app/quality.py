"""报价质量：垃圾过滤、封闭分类、product_key、链接探活、下架检测。"""
import re
from datetime import timedelta
from urllib.parse import urlsplit
from . import config, store
from .net import client

# —— 垃圾 ——
JUNK_TITLE = re.compile(
    r"(教程|须知必看|购买须知|售后须知|使用说明|下单前必|请先看|看完再买|温馨提示|公告|通知|"
    r"测试商品|测一测|勿拍|不要拍|仅测试|占位|示例|demo\b|sample\b|"
    r"充值教程|开通教程|绑定教程|如何使用|怎么用|补差价|差价专用|附加商品|邮费)", re.I)
JUNK_ZERO = re.compile(r"(免费领取|0元购|零元|面议|联系客服询价)", re.I)

def is_junk(o: dict) -> str | None:
    title = (o.get("title") or "") + " " + (o.get("product") or "")
    if JUNK_TITLE.search(title): return "教程/须知/公告/测试类非商品"
    if re.fullmatch(r"\s*(测试|test|tests?|测试\d*|111+|aaa+|123+)\s*", o.get("title") or "", re.I): return "测试占位"
    price = o.get("price")
    if price is not None and price <= 0:
        return "价格≤0 占位" if not JUNK_ZERO.search(title) else "免费领取/面议占位"
    if re.search(r"勿拍|不要拍|仅展示|不发货", title): return "明示勿拍/仅展示"
    return None

# —— 封闭分类：形态优先 ——
# 顺序很重要：更具体的在前
CAT_RULES = [
    ("gcp-trial", re.compile(r"gcp|google\s*cloud|云试用", re.I), re.compile(r"教程", re.I)),
    ("image-api", re.compile(
        r"nano\s*banana|香蕉.*生图|生图\s*api|gpt-image|dall-?e|flux\b|seedream|imagen|midjourney|"
        r"veo\b|kling|jimeng|即梦|grok-imagine|qwen-image|stable-?diffusion|wanx|kolors|luma|runway|sora", re.I), None),
    ("family", re.compile(r"家庭[组位车]|family\s*slot|拼车|车位|席位|共享位|team\s*席|子号.*席", re.I),
     re.compile(r"教程|须知", re.I)),
    ("verify", re.compile(r"(?<!未)(?<!不)(接码|接马)|kyc|实卡(?!充)|短信验证|手机号验证|验证码收|sms\b", re.I),
     re.compile(r"成品号|代充|cdk|订阅充|官方充|未接码|不接码", re.I)),
    ("payment", re.compile(r"虚拟卡|礼品卡|visa\b|mastercard|\b0刀\b|itunes|苹果卡", re.I),
     re.compile(r"接码|接马|成品", re.I)),
    ("email", re.compile(
        r"(?<![a-z])(gmail|outlook|hotmail|icloud|edu\.?邮箱|教育邮箱|邮箱母号|"
        r"谷歌邮箱|谷歌(?:免费)?(?:账号|帐号|号)|google\s*(?:account|mail)|微软邮箱|邮箱账号|隐私邮箱|(?:纯)?邮箱\b)", re.I),
     # 邮箱作载体的成品号/代充不算纯邮箱
     re.compile(r"成品号|独享号|代充|直充|cdk|plus\b|pro\s*x|claude|gemini\s*pro|grok\s*super|订阅", re.I)),
    ("topup", re.compile(
        r"代充|直充|官方充|cdk|卡密充|续费码|订阅充|官方渠道.*充|ios\s*充|卡充|秒充|自助充值", re.I),
     re.compile(r"教程|须知|接码|接马", re.I)),
    ("api-relay", re.compile(
        r"中转|按量付费|api\s*额度|额度卡|token\s*额度|\bapi\b.*站|"
        r"1m\s*token|/\$|/\$|/1m|/次\b|model_ratio|quota", re.I),
     re.compile(r"成品号|代充|接码|邮箱|cdk\b", re.I)),
    ("social", re.compile(
        r"telegram|tg\s*premium|推特|twitter|x\s*premium|supergro|apple\s*id|"
        r"多邻国|duolingo|reddit|discord|tiktok|netflix|spotify", re.I),
     re.compile(r"教程|接码", re.I)),
    ("ai-tool", re.compile(
        r"cursor|kiro|perplexity|suno|dreamina|muse\s*ai|windsurf|devin|copilot|"
        r"firefly|leonardo|midjourney\s*账号", re.I),
     re.compile(r"教程|须知|中转|api\s*额度", re.I)),
    # 大厂对话/编程账号成品号（放在 topup/email 之后）
    ("account", re.compile(
        r"chatgpt|chat\s*gpt|\bgpt\b|codex|openai|claude|anthropic|gemini|google\s*ai|"
        r"antigravity|反重力|\bgrok\b|xai\b|plus\b|pro\s*x?\d|team\b|business|"
        r"成品号|独享号|普号|白号|free\s*号|账密|带2fa", re.I),
     re.compile(r"教程|须知|中转站|按量", re.I)),
]

OBFUSCATE = [(re.compile(r"\bgro\s*k\b|\bgro(?=\d|\b)(?!up)", re.I), " grok "), (re.compile(r"\bcaude\b|cl[a@]ude", re.I), "claude"),
             (re.compile(r"c-odex|c0dex|co-dex", re.I), "codex"), (re.compile(r"g\s*pt|gp-t", re.I), "gpt"),
             (re.compile(r"\bg\s*(plus|pro)\b", re.I), r"gpt \1")]

def normalize_title(t: str) -> str:
    """卖家常用的规避写法还原：gro→grok、Caude→claude、C-odex→codex、G Plus→gpt plus。"""
    for rx, rep in OBFUSCATE: t = rx.sub(rep, t)
    return t

PRE_RULES = [
    # 卡网卖的 API 额度/余额/兑换码（与中转模型价隔离）
    ("api-credit", re.compile(
        r"api.{0,12}(cdk|额度|余额|兑换码|\d+\s*(刀|\$|美元|usd))|(\d+\s*(刀|美元|usd|\$))\s*(额度|余额|兑换码|卡密)|"
        r"(额度|余额)(卡密|兑换|补给|卡)|中转站?.{0,6}(赠额|额度|兑换)|算力点|token\s*额度|^\s*\d+\s*(刀|usd|额度)\s*$|"
        r"(seedance|image\s*2|生图|veo|sora|kling).{0,20}\d+\s*(刀|张|\$)|cny\s*\d+\s*=\s*usd|¥\s*\d+\s*=\s*\$|\(1:1\)兑换码|号池", re.I),
     re.compile(r"plus|pro\s*\d+x|\d+x\b|成品号|会员|订阅|代充|super\s*grok", re.I)),
    ("social", re.compile(
        r"[\U0001F1E6-\U0001F1FF]{2}\s*\+\d{1,4}|tgapi|纸飞机|tg\s*-?\s*\d+\s*月|telegram|facebook|instagram|whatsapp|"
        r"网易云|黑胶|腾讯视频|爱奇艺|优酷|芒果tv|百度网盘|夸克|华为视频|bilibili|b站大会员|美团|饿了么|qq音乐|酷狗|youtube\s*premium", re.I), None),
    ("verify", re.compile(r"giffgaff|运营商|esim|美国\+1|\+1\s*号|实体卡号|手机卡", re.I), None),
    ("topup", re.compile(r"学生认证|正价充|官方正价|代绑|链接代|升级\s*(plus|pro)", re.I), None),
    ("ai-tool", re.compile(
        r"adobe|express\s*premium|photoshop|canva|notion|grammarly|capcut|剪映|figma|gamma\.app|gamma\b|heygen|elevenlabs|"
        r"replit|cline|lovable|bolt\.new|v0\.dev|manus|genspark|lovart|adspower|闲鱼助手|dola|豆包|kimi\s*会员|poe\b|you\.com", re.I),
     re.compile(r"中转|api\s*额度", re.I)),
    ("family", re.compile(r"轮转|共享号|合租|多人共享", re.I), None),
]

def guess_category(text: str) -> str:
    t = normalize_title(text or "")
    # 中转模型价标题形态："model · $x/单位"
    if re.search(r"·\s*\$[\d.]+\s*/\s*(次|1M)", t) or re.search(r"@\s*\S+\s*$", t) and "/1M" in t:
        if re.search(r"image|dall|flux|seedream|veo|kling|imagine|banana|jimeng|midjourney", t, re.I):
            return "image-api"
        return "api-relay"
    for cat, pos, neg in PRE_RULES + CAT_RULES:
        if pos.search(t) and not (neg and neg.search(t)):
            return cat
    if re.search(r"plus|pro\s*\d*x|\d+x\b|ultra|super|max\s*x?\d*", t, re.I):
        return "account"
    return "other"

SUB_RULES = [
    ("家庭位", re.compile(r"家庭[组位]|family\s*slot|车位|拼车|共享位", re.I)),
    ("代充", re.compile(r"代充|直充|官方充|cdk|卡密充|续费|订阅充", re.I)),
    ("成品号", re.compile(r"成品号|独享号|成品\b|账密|带2fa|白号|普号", re.I)),
    ("接码", re.compile(r"接码|接马|sms|验证码|实卡", re.I)),
    ("邮箱", re.compile(r"邮箱|gmail|outlook|hotmail|icloud|edu", re.I)),
    ("API", re.compile(r"\bapi\b|中转|按量|额度|token|1m\s*token", re.I)),
]

def guess_subtypes(text: str) -> list[str]:
    t = text or ""
    return [name for name, rx in SUB_RULES if rx.search(t)]

# —— product_key：把同款商品归一 ——
# 品牌别名
BRANDS = [
    ("chatgpt", re.compile(r"chatgpt|chat\s*gpt|openai|\bgpt\b|codex|g\s*\+?\s*p\s*·?\s*t|g\s*plus|jpt", re.I)),
    ("claude", re.compile(r"claude|anthropic|\bcc\b", re.I)),
    ("gemini", re.compile(r"gemini|google\s*ai|antigravity|反重力|ai\s*ultra", re.I)),
    ("grok", re.compile(r"\bgrok\b|supergro|xai\b", re.I)),
    ("cursor", re.compile(r"cursor", re.I)),
    ("kiro", re.compile(r"kiro", re.I)),
    ("gmail", re.compile(r"gmail|谷歌邮箱|谷歌(?:免费)?(?:账号|帐号|号)|google\s*(?:account|mail)|谷歌.*邮箱", re.I)),
    ("outlook", re.compile(r"outlook|hotmail|微软邮箱", re.I)),
    ("icloud", re.compile(r"icloud", re.I)),
    ("gcp", re.compile(r"\bgcp\b|google\s*cloud", re.I)),
    ("telegram", re.compile(r"telegram|tg\s*premium", re.I)),
    ("x-premium", re.compile(r"x\s*premium|twitter\s*premium|推特", re.I)),
    ("apple-id", re.compile(r"apple\s*id", re.I)),
    ("visa", re.compile(r"visa|虚拟卡|0刀", re.I)),
]

TIER = [
    ("pro-20x", re.compile(r"pro\s*x?\s*20|20\s*x|20x|200\s*刀", re.I)),
    ("pro-5x", re.compile(r"pro\s*x?\s*5|5\s*x|5x|100\s*刀", re.I)),
    ("pro", re.compile(r"\bpro\b|max\b", re.I)),
    ("plus", re.compile(r"\bplus\b|plus月", re.I)),
    ("team", re.compile(r"\bteam\b|business|k12", re.I)),
    ("ultra", re.compile(r"ultra", re.I)),
    ("free", re.compile(r"\bfree\b|普号|白号|免费号|免费账号|免费帐号|普通号|新号|空白", re.I)),
]

FORM = [
    ("api-credit", PRE_RULES[0][1]),
    ("topup", re.compile(r"代充|直充|官方充|cdk|卡密充|续费|秒充|自助充", re.I)),
    ("family", re.compile(r"家庭|拼车|车位|席位|轮转|共享号|合租", re.I)),
    ("verify", re.compile(r"(?<!未)(?<!不)(接码|接马)|(?<!未)实卡(?!充)|sms", re.I)),
    ("email", re.compile(r"邮箱|gmail|outlook|hotmail|icloud", re.I)),
    ("account", re.compile(r"成品|独享|账密|带2fa|订阅号", re.I)),
]

DURATION = [
    ("1y", re.compile(r"12\s*个?月|一年|1\s*年|365", re.I)),
    ("18m", re.compile(r"18\s*个?月", re.I)),
    ("6m", re.compile(r"6\s*个?月|半年", re.I)),
    ("3m", re.compile(r"3\s*个?月|季", re.I)),
    ("1m", re.compile(r"1\s*个?月|月卡|30\s*天", re.I)),
    ("1w", re.compile(r"周卡|7\s*天|一周", re.I)),
]

def product_key(text: str) -> str:
    """归一化商品键，用于同款聚合。例：谷歌免费账号 / Gmail新号 / 谷歌邮箱 → gmail:email:free"""
    t = normalize_title(text or "")
    brand = next((b for b, rx in BRANDS if rx.search(t)), None)
    form = next((f for f, rx in FORM if rx.search(t)), None)
    tier = next((x for x, rx in TIER if rx.search(t)), None)
    dur = next((x for x, rx in DURATION if rx.search(t)), None)

    # 纯邮箱（无成品/代充信号）
    if brand in ("gmail", "outlook", "icloud") and form in (None, "email", "account") and not re.search(r"plus|pro|claude|gemini|成品号|代充|接码|接马", t, re.I):  # noqa: E501
        form = "email"
        if not tier and re.search(r"新号|全新|注册|空白|母号|free|普通|免费", t, re.I):
            tier = "free"
        return ":".join(x for x in (brand, form, tier) if x)

    # 谷歌免费账号 / Google 账号 无品牌时
    if not brand and re.search(r"谷歌.*(账号|帐号|号)|google\s*(account|账号)", t, re.I):
        brand = "gmail"
        form = form or "email"
        tier = tier or "free"

    if not brand and re.search(r"·\s*\$", t):  # 中转模型
        m = re.match(r"^\s*([a-z0-9._/-]+)", t, re.I)
        return f"relay:{(m.group(1) if m else t[:40]).lower()}"

    if form == "api-credit":   # 额度卡：品牌只认 AI 厂商，档位用面额
        if brand not in ("chatgpt", "claude", "gemini", "grok"): brand = None
        amt = re.search(r"(\d+(?:\.\d+)?)\s*(刀|美元|usd|\$|u\b)", t, re.I)
        tier = f"{amt.group(1)}usd" if amt else None
    parts = [brand or "misc", form or guess_category(t), tier, dur]
    if not brand:   # 无品牌：附加标题指纹，避免无关商品被并成一团
        slug = re.sub(r"[\W_]+", "", collapse_repeats(t).lower())[:24]
        parts.append(slug or "x")
    return ":".join(p for p in parts if p)


def collapse_repeats(t: str) -> str:
    """'A A A A' → 'A'（部分源标题被重复拼接）。"""
    t = re.sub(r"\s+", " ", (t or "").strip())
    m = re.fullmatch(r"(.{2,80}?)(?: \1)+(?: .{0,80})?", t)
    if m and t.startswith(m.group(1) + " " + m.group(1)): return m.group(1)
    return t

def canonical_product(text: str) -> str:
    """给人看的短名，来自 product_key。"""
    key = product_key(text)
    labels = {
        "gmail:email:free": "谷歌邮箱 / Gmail 新号",
        "gmail:email": "谷歌邮箱 / Gmail",
        "outlook:email:free": "Outlook / Hotmail 邮箱",
        "outlook:email": "Outlook / Hotmail 邮箱",
        "icloud:email": "iCloud 邮箱",
        "chatgpt:account:plus": "ChatGPT Plus 成品号",
        "chatgpt:topup:plus": "ChatGPT Plus 代充",
        "chatgpt:account:pro-20x": "ChatGPT Pro 20x 成品号",
        "chatgpt:topup:pro-20x": "ChatGPT Pro 20x 代充",
        "chatgpt:account:pro-5x": "ChatGPT Pro 5x 成品号",
        "chatgpt:topup:pro-5x": "ChatGPT Pro 5x 代充",
        "chatgpt:account:team": "ChatGPT Team / Business",
        "chatgpt:account:free": "ChatGPT Free / 普号",
        "chatgpt:verify": "ChatGPT / Codex 接码",
        "claude:account:pro": "Claude Pro 成品号",
        "claude:topup:pro": "Claude Pro 代充",
        "claude:account:pro-20x": "Claude Max 20x",
        "gemini:account:pro": "Gemini Pro 成品号",
        "gemini:topup:pro": "Gemini Pro 代充",
        "gemini:family": "Gemini 家庭组 / 车位",
        "grok:account": "Grok 成品号",
        "grok:topup": "Grok 代充",
        "cursor:account": "Cursor 账号",
        "gcp:account": "GCP 试用号",
        "visa:payment": "Visa 虚拟卡",
        "telegram:social": "Telegram Premium",
        "x-premium:social": "X Premium",
        "apple-id:social": "Apple ID",
    }
    if key in labels: return labels[key]
    # 模糊前缀
    for k, v in labels.items():
        if key.startswith(k): return v
    return None   # 无规范名：调用方回退到原标题，避免 product 自我拼接膨胀

# —— 下架 ——
OFF_SHELF = re.compile(
    r"商品未上架|商品已下架|已下架|商品不存在|不存在或已|商品已删除|商品已售罄|"
    r"goods\s*not\s*found|item\s*not\s*found|404\s*not\s*found|"
    r"该商品不存在|下架或删除|无法找到该商品|商品已失效|已售罄且下架|"
    r"如有疑问请联系商家", re.I)
CAPTCHA = re.compile(r"aliyun_waf|captcha|challenge-platform|cf-browser-verification|just a moment", re.I)

def classify_page(status: int, text: str, title: str = "") -> str:
    raw = text or ""
    blob = (title or "") + "\n" + raw[:50000]
    if status >= 400: return f"http_{status}"
    if CAPTCHA.search(blob): return "captcha"
    if OFF_SHELF.search(blob): return "off_shelf"
    if re.search(r"未上架|已下架|goodsNotExist|GOODS_NOT|item_not_item|offShelf|off_shelf", blob, re.I):
        return "off_shelf"
    visible = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>|\s+", " ", blob)
    if len(visible.strip()) < 40 and re.search(r'id=["\'](app|root|__nuxt)', raw, re.I):
        return "spa_empty"
    return "ok"

def apply_junk_and_category(batch_limit=100000):
    """重算 junk / category / product_key / product 显示名。"""
    d = store.db(); n_junk = n_cat = n_key = 0
    for o in d.offers.find({"ignored": {"$ne": True}},
                           {"title": 1, "product": 1, "price": 1, "category": 1, "tags": 1, "junk": 1, "source": 1}).limit(batch_limit):
        text = o.get("title") or o.get("product") or ""   # 只用原标题，避免 product 被反复拼接
        upd = {}
        reason = is_junk(o)
        if reason:
            upd.update(junk=True, junk_reason=reason); n_junk += 1
        elif o.get("junk"):
            d.offers.update_one({"_id": o["_id"]}, {"$unset": {"junk": 1, "junk_reason": 1}})
        # 中转源强制 api-relay / image-api
        if o.get("source") == "relay":
            cat = "image-api" if re.search(r"image|dall|flux|seedream|veo|kling|imagine|banana|jimeng", text, re.I) else "api-relay"
        else:
            cat = guess_category(text)
        key = product_key(text)
        card_api = o.get("source") != "relay"
        # product_key 形态优先：避免「未接码」等误伤导致分类漂移
        form = (key.split(":")[1] if ":" in key else "")
        form_to_cat = {"api-credit": "api-credit", "email": "email", "verify": "verify", "topup": "topup", "family": "family",
                       "account": "account", "payment": "payment", "social": "social"}
        if form in form_to_cat:
            cat = form_to_cat[form]
        if card_api and cat in ("api-relay", "image-api"):
            cat = "api-credit"   # 卡网卖的 API 额度/兑换码 ≠ 中转模型价，硬隔离
        name = canonical_product(text)
        subs = guess_subtypes(text)
        if cat != o.get("category"):
            upd["category"] = cat; n_cat += 1
        if key != o.get("product_key"):
            upd["product_key"] = key; n_key += 1
        name = name or collapse_repeats(o.get("title") or "")[:80]
        if name != o.get("product"):
            upd["product"] = name
        tags = list(dict.fromkeys([*(o.get("tags") or []), *subs]))
        if tags != (o.get("tags") or []): upd["tags"] = tags
        if upd: d.offers.update_one({"_id": o["_id"]}, {"$set": upd})
    return {"junk_marked": n_junk, "recategorized": n_cat, "product_keys": n_key}

def hide_no_url():
    r = store.db().offers.update_many(
        {"$or": [{"url": None}, {"url": ""}], "no_url": {"$ne": True}},
        {"$set": {"no_url": True, "link_status": "no_url"}})
    return r.modified_count

def hide_out_of_stock_aggregators():
    r = store.db().offers.update_many(
        {"source": {"$in": ["aigood", "apinav", "ldxp-showcase", "priceai"]}, "in_stock": False,
         "off_shelf": {"$ne": True}},
        {"$set": {"off_shelf": True, "link_status": "aggregator_oos", "off_shelf_at": store.now()}})
    return r.modified_count

def probe_links(limit=80, workers=3, delay=1.2):
    import time, logging
    from concurrent.futures import ThreadPoolExecutor
    log = logging.getLogger("mooo.quality")
    d = store.db()
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
            host = (urlsplit(u).hostname or "").lower()
            if any(host == x or host.endswith("." + x) for x in ("wzyp.cn", "ldxp.cn", "pay.ldxp.cn", "ldxp.net")):
                d.offers.update_one({"_id": o["_id"]}, {"$set": {"link_status": "captcha_host", "link_checked_at": store.now()}})
                return "captcha_host"
            with client(headers={"User-Agent": config.BROWSER_UA}) as c:
                m = re.search(r"catfk\.com/item/([A-Za-z0-9_-]+)", u)
                if m:
                    r = c.get("https://catfk.com/shopApi/Shop/goodsInfo", params={"link": m.group(1)}, timeout=15)
                    try: j = r.json()
                    except Exception: j = {}
                    msg = str(j.get("msg") or "")
                    if "不存在" in msg or "下架" in msg or (j.get("data") is None and j.get("code") == 0):
                        v = "off_shelf"
                    elif j.get("data"):
                        v = "ok"
                    else:
                        v = "unknown"
                    upd = {"link_status": v, "link_checked_at": store.now(), "link_api": "catfk.goodsInfo"}
                    if v == "off_shelf": upd.update(off_shelf=True, off_shelf_at=store.now())
                    elif v == "ok": upd["off_shelf"] = False
                    d.offers.update_one({"_id": o["_id"]}, {"$set": upd}); return v
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
