from fastapi.testclient import TestClient
from app.adapters.priceai import parse
from app.schema import Offer, guess_category
from app.net import ProxyPool
from app import crawler
from app.db import Base, engine
from app.main import app

SNAP = {"products": [{"name": "Gemini Pro", "platform": "Gemini", "top_offers": [
    {"title": "Gemini 家庭位", "price": 9.9, "status": "in_stock", "source_name": "s", "url": "https://x"}]}]}

def test_parse():
    o = list(parse(SNAP)); assert len(o) == 1 and o[0].category == "gemini" and o[0].in_stock

def test_category():
    assert guess_category("GCP $300 试用") == "gcp-trial"
    assert guess_category("Nano Banana 按张") == "nano-banana-api"

def test_proxy_pool_rotates():
    p = ProxyPool(["http://a:1", "http://b:2"]); got = {p.get() for _ in range(4)}
    assert got == {"http://a:1", "http://b:2"}
    assert ProxyPool().get() is None

class Fake:
    id, use_proxy, use_browser = "fake", False, False
    def fetch(self): return [Offer("fake", "Leonardo", "leonardo", "t", 1.5)]

class Boom(Fake):
    id = "boom"
    def fetch(self): raise RuntimeError("x")

def test_crawl_and_web():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    assert crawler.run_adapter(Fake()).count == 1
    assert crawler.run_adapter(Boom()).error
    c = TestClient(app)
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/api/offers", params={"category": "leonardo"}).json()[0]["price"] == 1.5
    r = c.get("/"); assert r.status_code == 200 and "Leonardo" in r.text
