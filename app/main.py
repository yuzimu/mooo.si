from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from . import config
from . import store
from .crawler import run_all
from .schema import CATEGORIES, SECTIONS
from . import views

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters.update(money=views.money, reltime=views.reltime)
templates.env.globals.update(cat_meta=views.cat_meta, SECTIONS=SECTIONS)

@asynccontextmanager
async def lifespan(app):
    store.ensure_indexes()
    sched = None
    if config.ENABLE_SCHEDULER:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime
        sched = BackgroundScheduler(timezone="UTC")
        sched.add_job(run_all, "interval", minutes=config.CRAWL_INTERVAL_MIN,
                      next_run_time=datetime.now(), max_instances=1, coalesce=True)
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
    return templates.TemplateResponse(request, "index.html", ctx)

@app.get("/search")
def search_page(request: Request, q: str = "", category: str = "", source: str = "",
                in_stock: bool = False, sort: str = "featured"):
    return index(request, q=q, category=category, source=source, in_stock=in_stock, sort=sort)

@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {})
