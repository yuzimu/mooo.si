import pytest
from app import config, net, targets, store
from app.pipeline import dedupe_key
from app.platforms import newapi, catfk
from app.discovery.telegram import extract, hint_for

def test_classify():
    assert targets.classify("https://catfk.com/shop/YiMeng")["key"] == "catfk:yimeng"
    assert targets.classify("https://catfk.com/item/xcw72f")["pending_item"] == "xcw72f"
    assert targets.classify("https://pay.ldxp.cn/shop/oak")["platform"] == "ldxp"
    assert targets.classify("t.me/AI_info_daily")["key"] == "tg:ai_info_daily"
    assert targets.classify("https://t.me/c/123/4") is None
    assert targets.classify("https://github.com/x/y") is None
    assert targets.classify("https://www.anyaigc.ai/register?aff=1", "relay")["key"] == "web:anyaigc.ai"

def test_upsert_merges_and_relay_wins():
    store.db().targets.delete_many({})
    targets.upsert([("https://foo.ai/a", "card_shop", "x", None)], "s1")
    targets.upsert([("https://foo.ai/b", "relay", "y", None), ("foo.ai", None, "z", None)], "s2")
    d = store.db().targets.find_one({"_id": "web:foo.ai"})
    assert d["mentions"] == 3 and d["type"] == "relay" and set(d["sources"]) == {"s1", "s2"}

def test_tg_extract():
    t = "中转站 https://api.x.com/v1 和 t.me/foo_bar 还有 shop.example.cn/item/1，"
    got = list(extract(t))
    assert "https://api.x.com/v1" in got and "t.me/foo_bar" in got and any("shop.example.cn" in g for g in got)
    assert hint_for(t) == "relay" and hint_for("自动发货 卡网") == "card_shop"

def test_newapi_parse():
    d = {"group_ratio": {"default": 1, "vip": 0.5},
         "data": [{"model_name": "gpt-5", "quota_type": 0, "model_ratio": 0.625, "enable_groups": ["default", "vip"]},
                  {"model_name": "nano-banana", "quota_type": 1, "model_price": 0.04, "enable_groups": ["default"]},
                  {"model_name": "foo-embed", "quota_type": 0, "model_ratio": 0.1}]}
    o = list(newapi.parse(d, "x", "https://x"))
    assert [x.extra["model"] for x in o] == ["gpt-5", "nano-banana"]
    assert o[0].price == 0.625 and o[1].price == 0.04 and o[1].category == "nano-banana-api"
    assert len(newapi.parse.rows) == 3

def test_catfk_parse():
    d = {"code": 1, "data": {"list": [{"name": "Gemini Pro 一年", "price": 9.9, "link": "https://catfk.com/item/a",
                                       "category": {"name": "Gemini"}, "user": {"nickname": "店", "token": "t"},
                                       "extend": {"stock_count": 0}}]}}
    o = list(catfk.parse(d))
    assert o[0].category in ("account","gcp-trial","gemini") and o[0].in_stock is False and o[0].seller == "店"

def test_dedupe_key():
    assert dedupe_key("https://www.catfk.com/item/abc/?x=1") == "catfk.com/item/abc"

def test_fail_closed(monkeypatch):
    monkeypatch.setattr(config, "PROXY_REQUIRED", True)
    monkeypatch.setattr(net, "pool", net.ProxyPool())
    with pytest.raises(net.ProxyUnavailable):
        net.client()
    with pytest.raises(net.ProxyUnavailable):
        net.check_proxy()


def test_partial_save_and_page_window():
    from app import store
    from app.adapters._util import page_window, page_advance
    store.db().discovery_state.delete_many({}); store.db().offers.delete_many({"source": "rot"})
    assert page_window("rot", 3) == [1, 2, 3]
    page_advance("rot", 3, 5, False); assert page_window("rot", 3, 5) == [1, 4, 5]
    page_advance("rot", 5, 5, False); assert page_window("rot", 3) == [1, 2, 3]
    def o(u):
        return {"source": "rot", "title": u, "product": u, "category": "other", "price": 1, "currency": "CNY", "seller": "s", "in_stock": True, "url": f"https://a.com/{u}"}
    store.save_run("rot", [o("a"), o("b")], partial=True)
    store.save_run("rot", [o("b"), o("c")], partial=True)
    assert store.db().offers.count_documents({"source": "rot"}) == 3
    store.db().offers.delete_many({"source": "rot"})


def test_purge_ignores_ai_products_and_blocks_readd():
    from app import store, targets
    col = store.db().targets
    targets.upsert([("https://cursor.so/", None, "awesome", store.now()), ("https://heck.ai/", None, "x", store.now()),
                    ("https://shop.goodcard.example/", "card_shop", "发卡", store.now())], "github-lists")
    assert col.find_one({"_id": "web:cursor.so"})["status"] == "ignored"   # 黑名单：入库即 ignored
    store.db().offers.insert_one({"source": "catfk", "target": "web:heck.ai", "title": "x", "price": 1})
    targets.purge()
    assert col.find_one({"_id": "web:heck.ai"})["status"] == "ignored"
    assert col.find_one({"_id": "web:shop.goodcard.example"})["status"] != "ignored"
    assert store.db().offers.find_one({"target": "web:heck.ai"})["ignored"] is True
    targets.upsert([("https://cursor.so/pricing", None, "again", store.now())], "offers")
    assert col.find_one({"_id": "web:cursor.so"})["status"] == "ignored"
    assert all(t["status"] != "ignored" for t in targets.search()[0])
    store.db().offers.delete_many({"target": "web:heck.ai"})


def test_cycle_lease_lock():
    from app import pipeline, store
    store.db().locks.delete_many({})
    assert pipeline._lock("cycle") is True
    assert pipeline._lock("cycle") is False        # 未完成不开新一轮
    pipeline.heartbeat()
    store.db().locks.update_one({"_id": "cycle"}, {"$set": {"until": store.now().replace(year=2000)}})
    assert pipeline._lock("cycle") is True         # 过期租约可接管
    store.db().locks.delete_many({})


def test_ldxp_canary_blocks_then_recovers(monkeypatch):
    """回归：canary 批量标记必须可回收。

    2026-10-12 一次探针失败把 18458 个 ldxp 目标全写成 blocked_captcha，而 run_targeted 会
    冷处理 blocked_captcha 7 天，且没有任何路径把它们放回来 —— 整条 ldxp 采集线就此停摆。
    """
    from app import pipeline, store
    from app.platforms import ldxp
    col = store.db().targets
    col.delete_many({"platform": "ldxp"})
    for tok in ("oak", "86ca7ta7"):
        col.insert_one({"_id": f"ldxp:{tok}", "platform": "ldxp", "type": "card_shop",
                        "url": f"https://pay.ldxp.cn/shop/{tok}", "status": "new"})
    # 探针被 ESA 拦：整批标记 + 打 canary 标记
    monkeypatch.setattr(ldxp, "probe", lambda c, tok: (False, "ldxp ShopApi 风控：WAF page on x"))
    assert pipeline._ldxp_canary(None, col) is False
    assert {d["status"] for d in col.find({"platform": "ldxp"})} == {"blocked_captcha"}
    assert all(d.get("ldxp_canary_blocked") for d in col.find({"platform": "ldxp"}))
    # 探针恢复：这批必须自动复位成 new 并清掉 fp，否则永远不再重试
    monkeypatch.setattr(ldxp, "probe", lambda c, tok: (True, "AI源头-oak"))
    assert pipeline._ldxp_canary(None, col) is True
    for d in col.find({"platform": "ldxp"}):
        assert d["status"] == "new" and "ldxp_canary_blocked" not in d and "fp" not in d
    # 逐个真·风控的目标不受 reset 影响
    col.insert_one({"_id": "ldxp:realwaf", "platform": "ldxp", "status": "blocked_captcha", "fp_at": store.now()})
    pipeline._ldxp_canary(None, col)
    assert col.find_one({"_id": "ldxp:realwaf"})["status"] == "blocked_captcha"
    col.delete_many({"platform": "ldxp"})
