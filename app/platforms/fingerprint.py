"""识别目标站点平台：new-api / one-api（/api/status）、链动小铺/CATFK（shopApi）、独角数卡、异次元、ESA 滑块等。"""
import re
import httpx

ESA = re.compile(r"aliyun.{0,40}captcha|nocaptcha|AliyunCaptcha|acw_sc__v2|_waf_bd8ce2ce37", re.I)
CF_CHALLENGE = re.compile(r"cf-chl|challenge-platform|Just a moment\.\.\.", re.I)

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
    elif "dujiaoka" in low or "独角数卡" in html: plat = "dujiaoka"
    elif "acg-faka" in low or "异次元" in html or "/user/api/index/" in low: plat = "acg-faka"
    elif "new api" in low or "new-api" in low: plat = "new-api"
    elif "one api" in low or "one-api" in low: plat = "one-api"
    else: plat = None
    return {"platform": plat, "status": "ok" if plat else "unknown", "name": title}
