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
    assert o[0].category == "gemini" and o[0].in_stock is False and o[0].seller == "店"

def test_dedupe_key():
    assert dedupe_key("https://www.catfk.com/item/abc/?x=1") == "catfk.com/item/abc"

def test_fail_closed(monkeypatch):
    monkeypatch.setattr(config, "PROXY_REQUIRED", True)
    monkeypatch.setattr(net, "pool", net.ProxyPool())
    with pytest.raises(net.ProxyUnavailable):
        net.client()
    with pytest.raises(net.ProxyUnavailable):
        net.check_proxy()
