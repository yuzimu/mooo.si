from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import Response, RedirectResponse, PlainTextResponse
from urllib.parse import urlsplit, quote
from fastapi.templating import Jinja2Templates
from . import config
from . import store, targets
from .schema import CATEGORIES, SECTIONS
from . import views

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters.update(money=views.money, reltime=views.reltime)
templates.env.globals.update(cat_meta=views.cat_meta, SECTIONS=SECTIONS, SITE_URL=config.SITE_URL)

def _go(url):
    from urllib.parse import quote
    return "/go?url=" + quote(url or "", safe="") if url else "#"

TYPE_PATH = {"card_shop": "shop", "relay": "relay", "tg": "tg", "unknown": "site"}
templates.env.filters.update(go=_go, target_path=lambda slug, typ: f"/{TYPE_PATH.get(typ, 'site')}/{slug}")

@asynccontextmanager
async def lifespan(app):
    store.ensure_indexes(); targets.ensure_indexes()
    sched = None
    if config.ENABLE_SCHEDULER:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime
        from . import pipeline
        sched = BackgroundScheduler(timezone=config.TZ)
        # 每 CRAWL_EVERY_HOURS 小时一轮（默认 2h，整点 + 0~10 分钟抖动）：代理检查 → 聚合源 → 发现 → 定向抓取 → 去重
        sched.add_job(pipeline.cycle, "cron", hour=f"*/{config.CRAWL_EVERY_HOURS}", minute=7, jitter=600,
                      max_instances=1, coalesce=True, misfire_grace_time=3600, id="cycle")
        if store.db().offers.estimated_document_count() == 0:  # 首次启动空库时立即跑一轮
            sched.add_job(pipeline.cycle, next_run_time=datetime.now())
        sched.start()
    yield
    if sched: sched.shutdown(wait=False)

app = FastAPI(title="mooo.si", lifespan=lifespan)

@app.get("/healthz")
def healthz():
    store.db().command("ping"); return {"ok": True}

def _params(q, category, source, in_stock, min_price, max_price):
    return dict(q=q or None, category=category or None, source=source or None, in_stock=in_stock,
                min_price=min_price, max_price=max_price)

@app.get("/api/search")
def api_search(q: str = "", category: str = "", source: str = "", in_stock: bool = False,
               min_price: float | None = None, max_price: float | None = None, sort: str = "price",
               limit: int = Query(50, le=500), offset: int = Query(0, ge=0)):
    items, total = store.search(limit=limit, skip=offset, sort=sort,
                                **_params(q, category, source, in_stock, min_price, max_price))
    return {"total": total, "offset": offset, "items": [store.to_json(o) for o in items]}

@app.get("/api/offers")
def api_offers(q: str | None = None, category: str | None = None, in_stock: bool = False,
               source: str | None = None, limit: int = Query(200, le=1000)):
    items, _ = store.search(limit=limit, **_params(q, category, source, in_stock, None, None))
    return [store.to_json(o) for o in items]

@app.get("/")
def index(request: Request, q: str = "", category: str = "", source: str = "", section: str = "",
          in_stock: bool = False, sort: str = "featured", page: int = 1, partial: bool = False):
    cats = {c for c, m in CATEGORIES.items() if m[2] == section} if section in SECTIONS else None
    base = store.all_offers(cats)
    offers, total = store.search(limit=3000, sort="price", categories=cats,
                                 **_params(q, category, source, in_stock, None, None))
    groups = views.group_products(offers, sort)
    page = max(page, 1); per = config.GROUPS_PER_PAGE
    page_groups = groups[(page - 1) * per: page * per]
    has_more = page * per < len(groups)
    if partial:
        r = templates.TemplateResponse(request, "_groups.html", {"groups": page_groups})
        r.headers["X-Has-More"] = "1" if has_more else "0"
        return r
    runs = store.recent_runs()
    last_ok = next((r for r in runs if not r.error), None)
    ctx = {
        "q": q, "category": category, "source": source, "section": section, "in_stock": in_stock, "sort": sort,
        "groups": page_groups, "groups_total": len(groups), "page": page, "has_more": has_more,
        "shown": len(page_groups) + (page - 1) * per, "config_per": per, "cats": views.category_cards(base),
        "cheapest": views.cheapest(base), "sources": sorted({o.source for o in base}),
        "stats": {"offers": len(base), "products": len({o.product for o in base}),
                  "sources": len({o.source for o in base}), "sellers": len({o.seller for o in base}),
                  "updated": last_ok.started_at if last_ok else None},
        "result_count": total,
    }
    ctx["seo"] = seo_index(request, category, q, section, ctx)
    return templates.TemplateResponse(request, "index.html", ctx)

def seo_index(request, category, q, section, ctx):
    from .views import cat_meta
    base = config.SITE_URL
    if category:
        m = cat_meta(category); title = f"{m['label']} 价格行情与最低价 · mooo.si"
        desc = f"{m['label']} 全网报价对比：{ctx['result_count']} 条报价，多家卖家同款比价，每 2 小时更新。"
        canonical = f"{base}/c/{category}"
    elif q:
        title, desc, canonical = f"「{q}」报价搜索 · mooo.si", f"搜索「{q}」的 AI 账号、卡网与中转报价。", f"{base}/search?q={quote(q)}"
    else:
        title = "mooo.si · AI 账号 / 卡网 / API 中转 比价雷达"
        desc = f"聚合 {ctx['stats']['offers']} 条 AI 卡网、API 中转、AI 工具报价，ChatGPT、Claude、Gemini、Grok 同款多家卖家实时比价。"
        canonical = base + "/"
    items = [{"@type": "ListItem", "position": i + 1, "item": {
        "@type": "Product", "name": g["name"], "category": cat_meta(g["category"])["label"],
        "offers": {"@type": "AggregateOffer", "lowPrice": g["min"], "highPrice": g["max"], "priceCurrency": g["currency"],
                   "offerCount": len(g["offers"])}}} for i, g in enumerate(ctx["groups"][:20])]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "mooo.si", "url": base + "/", "inLanguage": "zh-CN",
           "potentialAction": {"@type": "SearchAction", "target": base + "/search?q={search_term_string}",
                               "query-input": "required name=search_term_string"}},
          {"@context": "https://schema.org", "@type": "ItemList", "name": title, "itemListElement": items}]
    return {"title": title, "description": desc, "canonical": canonical, "jsonld": ld,
            "noindex": bool(q or ctx["source"] or ctx["in_stock"] or ctx["page"] > 1)}

@app.get("/search")
def search_page(request: Request, q: str = "", category: str = "", source: str = "",
                in_stock: bool = False, sort: str = "featured", page: int = 1, partial: bool = False):
    # 必须透传 page/partial：否则"加载更多"拿到整页 HTML 插进 #groups，页面重复、移动端 viewport 错乱
    return index(request, q=q, category=category, source=source, in_stock=in_stock, sort=sort, page=page, partial=partial)

@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"seo": {"title": "关于 mooo.si · 联系方式与提交店铺/中转",
        "description": "mooo.si 是开源的 AI 卡网、API 中转、AI 工具报价聚合站。联系方式 ykj@mail.grokbot.com，欢迎投递店铺与中转站。"}})

TARGET_PAGES = {"shops": ("card_shop", "卡网店铺", "store"), "relays": ("relay", "API 中转站", "network"),
                "tg": ("tg", "TG 群组 / 频道", "send")}

def _target_ctx(kind, q, platform, status, page):
    ctx = _target_ctx_inner(kind, q, platform, status, page)
    base = config.SITE_URL
    ctx["seo"] = {"title": f"{ctx['title']}监控列表（{ctx['total']}）· mooo.si",
                  "description": f"mooo.si 自动发现并监控的{ctx['title']}：共 {ctx['total']} 个，含平台识别、状态与报价数量，每 2 小时巡检。",
                  "canonical": f"{base}/{kind}", "noindex": bool(q or platform or status or page > 1),
                  "jsonld": [{"@context": "https://schema.org", "@type": "ItemList", "name": ctx["title"],
                              "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": t.get("name") or t.get("slug"),
                                                   "url": f"{base}/{TYPE_PATH.get(t.get('type'), 'site')}/{t.get('slug')}"}
                                                  for i, t in enumerate(ctx["items"])]}]}
    return ctx

def _target_ctx_inner(kind, q, platform, status, page):
    ttype, title, icon = TARGET_PAGES[kind]
    per = 30
    items, total = targets.search(type=ttype, q=q or None, platform=platform or None, status=status or None,
                                  limit=per, skip=(max(page, 1) - 1) * per)
    plats = sorted({d for d in store.db().targets.distinct("platform", {"type": ttype}) if d})
    stats = list(store.db().targets.aggregate([{"$match": {"type": ttype}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]))
    return {"kind": kind, "title": title, "icon": icon, "items": items, "total": total, "q": q, "platform": platform,
            "status": status, "page": max(page, 1), "per": per, "platforms": plats,
            "status_counts": {d["_id"] or "new": d["n"] for d in stats}}

@app.get("/shops")
def shops_page(request: Request, q: str = "", platform: str = "", status: str = "", page: int = 1):
    return templates.TemplateResponse(request, "targets.html", _target_ctx("shops", q, platform, status, page))

@app.get("/relays")
def relays_page(request: Request, q: str = "", platform: str = "", status: str = "", page: int = 1):
    return templates.TemplateResponse(request, "targets.html", _target_ctx("relays", q, platform, status, page))

@app.get("/tg")
def tg_page(request: Request, q: str = "", platform: str = "", status: str = "", page: int = 1):
    return templates.TemplateResponse(request, "targets.html", _target_ctx("tg", q, platform, status, page))

@app.get("/api/targets")
def api_targets(type: str = "", q: str = "", platform: str = "", status: str = "",
                limit: int = Query(50, le=500), offset: int = Query(0, ge=0)):
    items, total = targets.search(type=type or None, q=q or None, platform=platform or None, status=status or None,
                                  limit=limit, skip=offset)
    for d in items:
        d["id"] = d.pop("_id"); d.pop("history", None); d.pop("refs", None)
    return {"total": total, "items": items}


@app.get("/c/{category}")
def category_page(request: Request, category: str, in_stock: bool = False, sort: str = "featured", page: int = 1,
                  source: str = "", partial: bool = False):
    if category not in CATEGORIES: raise HTTPException(404)
    return index(request, category=category, source=source, in_stock=in_stock, sort=sort, page=page, partial=partial)

def _target_page(request, typ, slug):
    t = store.db().targets.find_one({"slug": slug, "type": typ}) if typ else store.db().targets.find_one({"slug": slug})
    if not t: raise HTTPException(404)
    t["host"] = urlsplit(t["url"]).hostname
    offers = [store._ns(d) for d in store.db().offers.find({"target": t["_id"], "dup": {"$ne": True}, "ignored": {"$ne": True}},
                                                              {"kw": 0}).sort("price", 1).limit(500)]
    rp = store.db().relay_prices.find_one({"_id": t["_id"]}) or {}
    back = {"card_shop": ("/shops", "卡网店铺"), "relay": ("/relays", "API 中转站"), "tg": ("/tg", "TG 群组 / 频道")}.get(t["type"], ("/", "首页"))
    kind = TYPE_PATH.get(t["type"], "site")
    name = t.get("name") or t["host"]
    label = {"card_shop": "卡网店铺", "relay": "API 中转站", "tg": "TG 频道"}.get(t["type"], "站点")
    groups = views.group_products(offers, "price")
    ld = {"@context": "https://schema.org", "@type": "Store" if t["type"] == "card_shop" else "Organization", "name": name,
          "url": f"{config.SITE_URL}/{kind}/{slug}", "sameAs": [t["url"]]}
    if offers:
        ld["makesOffer"] = [{"@type": "Offer", "name": o.title[:100], "price": o.price, "priceCurrency": o.currency,
                             "availability": "https://schema.org/InStock" if o.in_stock else "https://schema.org/OutOfStock"} for o in offers[:30]]
    seo = {"title": f"{name} · {label}报价与监控 · mooo.si",
           "description": f"{name}（{t['host']}）{label}信息：平台 {t.get('platform') or '未知'}，"
                          f"{len(offers) or len(rp.get('models') or [])} 条报价/模型价格，提及 {t.get('mentions', 0)} 次，每 2 小时巡检。",
           "canonical": f"{config.SITE_URL}/{kind}/{slug}", "jsonld": [ld], "noindex": not (offers or rp.get("models"))}
    return templates.TemplateResponse(request, "target.html", {"t": t, "groups": groups, "offer_count": len(offers), "models": rp.get("models"),
                                                               "back_href": back[0], "back_label": back[1], "seo": seo})

@app.get("/shop/{slug}")
def shop_detail(request: Request, slug: str): return _target_page(request, "card_shop", slug)

@app.get("/relay/{slug}")
def relay_detail(request: Request, slug: str): return _target_page(request, "relay", slug)

@app.get("/tg/{slug}")
def tg_detail(request: Request, slug: str): return _target_page(request, "tg", slug)

@app.get("/site/{slug}")
def site_detail(request: Request, slug: str): return _target_page(request, None, slug)

@app.get("/go")
def go(request: Request, url: str = "", ok: int = 0):
    """外链中转：仅允许 http/https 且域名属于已收录目标；默认显示风险提示页，需点击确认（ok=1 来自页内弹窗确认）。"""
    s = urlsplit(url)
    valid = s.scheme in ("http", "https") and bool(s.hostname) and "@" not in (s.netloc or "") and targets.host_allowed(s.hostname)
    if valid and ok == 1:
        return RedirectResponse(url, status_code=302, headers={"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})
    r = templates.TemplateResponse(request, "go.html", {"url": url, "host": s.hostname, "valid": valid,
                                                        "seo": {"title": "即将离开 mooo.si", "noindex": True}},
                                   status_code=200 if valid else 400)
    r.headers["X-Robots-Tag"] = "noindex, nofollow"
    return r

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nDisallow: /go\nDisallow: /api/\nDisallow: /*?*partial=\n\nSitemap: {config.SITE_URL}/sitemap.xml\n"

@app.get("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape
    base = config.SITE_URL; now = store.now().strftime("%Y-%m-%d")
    urls = [(f"{base}/", "hourly", "1.0"), (f"{base}/shops", "daily", "0.8"), (f"{base}/relays", "daily", "0.8"),
            (f"{base}/tg", "daily", "0.6"), (f"{base}/about", "monthly", "0.3")]
    used = set(store.db().offers.distinct("category", {"dup": {"$ne": True}, "ignored": {"$ne": True}}))
    urls += [(f"{base}/c/{c}", "daily", "0.7") for c in CATEGORIES if c in used]
    for t in store.db().targets.find({"$or": [{"health.offers": {"$gt": 0}}, {"health.models": {"$gt": 0}}]},
                                     {"slug": 1, "type": 1}).limit(20000):
        urls.append((f"{base}/{TYPE_PATH.get(t.get('type'), 'site')}/{t['slug']}", "daily", "0.5"))
    body = "".join(f"<url><loc>{escape(u)}</loc><lastmod>{now}</lastmod><changefreq>{f}</changefreq><priority>{p}</priority></url>"
                   for u, f, p in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, media_type="application/xml")

@app.get("/og.svg")
def og_image():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"><defs><linearGradient id="g" x1="0" x2="1">'
           '<stop offset="0" stop-color="#38bdf8"/><stop offset=".5" stop-color="#8b5cf6"/><stop offset="1" stop-color="#e879f9"/></linearGradient></defs>'
           '<rect width="1200" height="630" fill="#05070d"/><text x="80" y="300" font-size="96" font-weight="800" fill="#fff" '
           'font-family="sans-serif">mooo.si</text>'
           '<text x="80" y="400" font-size="56" font-weight="700" fill="url(#g)" font-family="sans-serif">AI 资源比价雷达</text></svg>')
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
