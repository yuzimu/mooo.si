from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Query, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from . import config
from .db import Base, engine, Session, OfferRow, CrawlRun
from .crawler import run_all

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
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

def get_session():
    with Session() as s: yield s

def query(s, q=None, category=None, in_stock=None, limit=500):
    st = select(OfferRow)
    if q: st = st.where(OfferRow.title.contains(q) | OfferRow.product.contains(q))
    if category: st = st.where(OfferRow.category == category)
    if in_stock: st = st.where(OfferRow.in_stock.is_(True))
    return s.scalars(st.order_by(OfferRow.price).limit(limit)).all()

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.get("/api/offers")
def api_offers(q: str | None = None, category: str | None = None, in_stock: bool = False,
               limit: int = Query(200, le=1000), s=Depends(get_session)):
    cols = [c.name for c in OfferRow.__table__.columns]
    return [{c: getattr(o, c) for c in cols} for o in query(s, q, category, in_stock, limit)]

@app.get("/")
def index(request: Request, q: str = "", category: str = "", in_stock: bool = False,
          s=Depends(get_session)):
    cats = [c for (c,) in s.execute(select(OfferRow.category).distinct().order_by(OfferRow.category))]
    last = s.scalars(select(CrawlRun).order_by(CrawlRun.id.desc()).limit(5)).all()
    total = s.scalar(select(func.count(OfferRow.id)))
    return templates.TemplateResponse(request, "index.html", {
        "offers": query(s, q, category, in_stock), "cats": cats, "q": q, "category": category,
        "in_stock": in_stock, "runs": last, "total": total})
