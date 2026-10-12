from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Float, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from . import config

def now(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass

class OfferRow(Base):
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    product: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    seller: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    stock: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[str | None] = mapped_column(String(40))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

def make_engine(url=None):
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///./"):
        import os
        os.makedirs(os.path.dirname(url[len("sqlite:///"):]) or ".", exist_ok=True)
    kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kw)

engine = make_engine()
Session = sessionmaker(engine, expire_on_commit=False)
