"""识别目标站点平台：new-api / one-api（/api/status）、链动小铺/CATFK（shopApi）、独角数卡、异次元、ESA 滑块等。"""
import re
import httpx

ESA = re.compile(r"aliyun.{0,40}captcha|nocaptcha|AliyunCaptcha|acw_sc__v2|_waf_bd8ce2ce37", re.I)
CF_CHALLENGE = re.compile(r"cf-chl|challenge-platform|Just a moment\.\.\.", re.I)

def _dujiao_next(c, base):
    try:
        r = c.get(base + "/api/v1/public/config", timeout=10)
        return r.status_code == 200 and (r.json() or {}).get("status_code") == 0
    except Exception:  # noqa: BLE001
        return False


def fingerprint(c: httpx.Client, t: dict) -> dict:
    """返回 {"platform", "status", "name", "note"}；status: ok / blocked_captcha / blocked_cf / down / unknown"""
    if t.get("platform") == "ldxp":
        # ldxp 店铺 ShopApi 公开可直采（无需登录），先轻探针验证再决定
        from .ldxp import probe as _ldxp_probe
        token = t.get("_id", "").split(":", 1)[1] if ":" in t.get("_id", "") else ""
        if not token:
            return {"platform": "ldxp", "status": "unknown", "note": "缺少店铺 token"}
        ok, note = _ldxp_probe(c, token)
        if ok:
            return {"platform": "ldxp", "status": "ok", "name": note}
        if "风控" in note:
            return {"platform": "ldxp", "status": "blocked_captcha", "note": note}
        return {"platform": "ldxp", "status": "down", "note": note}
    if t.get("platform") == "catfk": return {"platform": "catfk", "status": "ok"}
    if t["type"] == "tg": return {"platform": "telegram", "status": "ok" if t.get("tg_public") else "private"}
    base = t["url"].rstrip("/")
    try:
        r = c.get(base + "/api/status", timeout=12)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            d = (r.json() or {}).get("data") or {}
            if "quota_per_unit" in d or "system_name" in d:
                plat = "new-api" if ("version" in d and "new" in str(d.get("version", "")).lower()) or "price" in d or "setup" in d \
                    else "one-api"
                return {"platform": plat, "status": "ok", "name": d.get("system_name"),
                        "meta": {k: d.get(k) for k in ("version", "quota_per_unit", "price", "display_in_currency", "usd_exchange_rate")}}
        r = c.get(base + "/api/v1/settings/public", timeout=12)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            j = r.json() or {}
            d = j.get("data") if isinstance(j.get("data"), dict) else {}
            if j.get("code") == 0 and any(k in d for k in ("registration_enabled", "site_name", "registration", "email_verify_enabled")) or \
               any(k.startswith("registration") for k in d):
                # Wei-Shaw/sub2api：订阅/拼车型中转，模型价格需登录（/api/v1/plans 受 JWT 保护）
                return {"platform": "sub2api", "status": "private", "name": d.get("site_name"),
                        "note": "sub2api：价格/套餐需登录，仅做存活监控"}
        h = c.get(base + "/", timeout=12)
    except httpx.HTTPError as e:
        return {"platform": None, "status": "down", "note": type(e).__name__}
    html = h.text[:200000]
    if h.status_code in (403, 503) and CF_CHALLENGE.search(html): return {"platform": None, "status": "blocked_cf"}
    if ESA.search(html): return {"platform": None, "status": "blocked_captcha", "note": "阿里云 ESA/WAF 验证"}
    if h.status_code >= 500: return {"platform": None, "status": "down", "note": f"HTTP {h.status_code}"}
    title = (re.search(r"<title>([^<]{0,80})", html) or [None, None])[1]
    low = html.lower()
    if "/shopapi/" in low or "package/shop/assets" in low: plat = "lianDong-shop"
    elif re.search(r"/assets/(unicorn|luna|hyper)/", low): plat = "dujiaoka"
    elif "/assets/user/css/" in low and "/assets/common/" in low: plat = "acg-faka"
    elif "vendor-vue-i18n" in low and _dujiao_next(c, base): plat = "dujiao-next"
    elif "ai api gateway" in low or "sub2api" in low: plat = "sub2api"
    elif "dujiaoka" in low or "独角数卡" in html: plat = "dujiaoka"
    elif "acg-faka" in low or "异次元" in html or "/user/api/index/" in low: plat = "acg-faka"
    elif "new api" in low or "new-api" in low: plat = "new-api"
    elif "one api" in low or "one-api" in low: plat = "one-api"
    else: plat = None
    if plat == "sub2api": return {"platform": plat, "status": "private", "name": title, "note": "sub2api：价格需登录"}
    return {"platform": plat, "status": "ok" if plat else "unknown", "name": title}
