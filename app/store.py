"""MongoDB 存储层：原始数据 raw、标准化报价 offers、抓取记录 crawl_runs。

中文搜索：不依赖 Mongo text 索引（不支持中文分词），而是写入时生成 `kw` 关键词数组
（CJK 单字 + 双字 n-gram、英文/数字词及其前缀），建多键索引，查询时同样切词后 `$all` 匹配。
"""
import re
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from pymongo import MongoClient, ASCENDING, DESCENDING
from . import config

CJK = re.compile(r"[\u3400-\u9fff]+")
WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

def now(): return datetime.now(timezone.utc)

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("／", "/")).strip()

def tokens(text: str, prefixes=True) -> set[str]:
    t = normalize(text); out = set()
    for run in CJK.findall(t):
        out.update(run)
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    for w in WORD.findall(t):
        out.add(w)
        if prefixes and len(w) > 2: out.update(w[:i] for i in range(2, len(w)))
    return out

def query_tokens(q: str) -> list[str]:
    """查询端：CJK 取双字（单字词则取单字），英文取整词（可匹配前缀）。"""
    t = normalize(q); out = []
    for run in CJK.findall(t):
        out += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
    out += WORD.findall(t)
    return list(dict.fromkeys(out))

_client = None
def db():
    global _client
    if _client is None:
        if config.MONGO_URL.startswith("mongomock://"):
            import mongomock
            _client = mongomock.MongoClient()
        else:
            _client = MongoClient(config.MONGO_URL, serverSelectionTimeoutMS=5000, tz_aware=True)
    return _client[config.MONGO_DB]

def ensure_indexes():
    d = db()
    d.offers.create_index([("category", ASCENDING), ("in_stock", ASCENDING), ("price", ASCENDING)])
    d.offers.create_index([("source", ASCENDING), ("price", ASCENDING)])
    d.offers.create_index([("product", ASCENDING), ("price", ASCENDING)])
    d.offers.create_index([("kw", ASCENDING)])
    d.offers.create_index([("price", ASCENDING)])
    d.raw.create_index([("source", ASCENDING), ("fetched_at", DESCENDING)])
    d.raw.create_index("fetched_at", expireAfterSeconds=int(timedelta(days=config.RAW_RETENTION_DAYS).total_seconds()))
    d.crawl_runs.create_index([("started_at", DESCENDING)])
    d.offers.create_index([("target", ASCENDING)])
    d.offers.create_index([("dedupe_key", ASCENDING)])
    d.offers.create_index([("dup", ASCENDING), ("category", ASCENDING), ("price", ASCENDING)])

def save_run(source: str, offers: list[dict], raw=None, error=None, partial=False):
    d = db(); ts = now()
    run = {"source": source, "started_at": ts, "count": len(offers), "error": error}
    if error is None:
        if raw is not None: d.raw.insert_one({"source": source, "fetched_at": ts, "payload": raw})
        docs = []
        for o in offers:
            o = dict(o); o["fetched_at"] = ts; o["dedupe_key"] = _dkey(o.get("url"))
            o["kw"] = sorted(tokens(" ".join([o.get("product") or "", o.get("title") or "",
                                              o.get("seller") or "", " ".join(o.get("tags") or [])])))
            docs.append(o)
        if partial:
            # 轮转分页来源：按链接/标题替换本轮看到的报价；超过 OFFER_TTL_H 未再出现的才删除
            keys = [o["dedupe_key"] for o in docs if o.get("dedupe_key")]
            titles = [o.get("title") for o in docs if not o.get("dedupe_key")]
            d.offers.delete_many({"source": source, "target": {"$exists": False},
                                  "$or": [{"dedupe_key": {"$in": keys}}, {"dedupe_key": None, "title": {"$in": titles}}]})
            from datetime import timedelta
            d.offers.delete_many({"source": source, "target": {"$exists": False}, "fetched_at": {"$lt": ts - timedelta(hours=config.OFFER_TTL_H)}})
        else:
            d.offers.delete_many({"source": source, "target": {"$exists": False}})   # 每个来源保留最新快照
        if docs: d.offers.insert_many(docs)
    d.crawl_runs.insert_one(run)
    return SimpleNamespace(**run)

def _dkey(url):
    from .pipeline import dedupe_key
    return dedupe_key(url)

def save_target_offers(target_id: str, offers: list[dict]):
    d = db(); ts = now(); docs = []
    for o in offers:
        o = dict(o); o["fetched_at"] = ts; o["target"] = target_id; o["dedupe_key"] = _dkey(o.get("url"))
        o["kw"] = sorted(tokens(" ".join([o.get("product") or "", o.get("title") or "", o.get("seller") or "",
                                          " ".join(o.get("tags") or [])])))
        docs.append(o)
    d.offers.delete_many({"target": target_id})
    if docs: d.offers.insert_many(docs)

def build_filter(q=None, category=None, source=None, in_stock=False, categories=None,
                 min_price=None, max_price=None):
    f = {"dup": {"$ne": True}, "ignored": {"$ne": True}, "junk": {"$ne": True},
         "off_shelf": {"$ne": True}, "no_url": {"$ne": True}}
    if q:
        qt = query_tokens(q)
        f["kw"] = {"$all": qt} if qt else {"$exists": True}
    if category: f["category"] = category
    elif categories is not None: f["category"] = {"$in": list(categories)}
    if source: f["source"] = source
    if in_stock: f["in_stock"] = True
    if min_price is not None or max_price is not None:
        f["price"] = {k: v for k, v in (("$gte", min_price), ("$lte", max_price)) if v is not None}
    return f

SORTS = {"price": [("price", 1)], "-price": [("price", -1)], "new": [("fetched_at", -1)]}

def search(limit=200, sort="price", skip=0, **kw):
    f = build_filter(**kw)
    cur = db().offers.find(f, {"kw": 0}).sort(SORTS.get(sort, SORTS["price"])).skip(skip).limit(limit)
    return [_ns(d) for d in cur], db().offers.count_documents(f)

def all_offers(categories=None):
    f = {"dup": {"$ne": True}, "ignored": {"$ne": True}, "junk": {"$ne": True},
         "off_shelf": {"$ne": True}, "no_url": {"$ne": True}}
    if categories is not None: f["category"] = {"$in": list(categories)}
    return [_ns(d) for d in db().offers.find(f, {"kw": 0})]

def recent_runs(n=20):
    return [SimpleNamespace(**r) for r in db().crawl_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(n)]

def _ns(d):
    d = dict(d); d["id"] = str(d.pop("_id", ""))
    d.setdefault("tags", []); d.setdefault("seller", None); d.setdefault("in_stock", None)
    return SimpleNamespace(**d)

def to_json(o):
    d = dict(vars(o))
    if isinstance(d.get("fetched_at"), datetime): d["fetched_at"] = d["fetched_at"].isoformat()
    return d
