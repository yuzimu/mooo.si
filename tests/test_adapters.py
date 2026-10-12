import json
from pathlib import Path
from app.adapters import aigood, apinav, ldxp_showcase, oai9, ldxp_merchant, ALL
from app.adapters._util import nuxt_payload, parse_price

F = Path(__file__).parent / "fixtures"

def test_parse_price():
    assert parse_price("按量付费 ￥1起充") == (1.0, "CNY")
    assert parse_price("CNY 0.55") == (0.55, "CNY")

def test_aigood_html():
    o = list(aigood.parse((F / "aigood.html").read_text(encoding="utf-8")))
    assert len(o) >= 20 and all(x.price > 0 for x in o) and any(x.in_stock for x in o)
    assert all(x.url and x.url.startswith("http") for x in o)

def test_apinav_nuxt():
    sites = list(apinav.parse_sites(nuxt_payload((F / "apinav_sites.html").read_text(encoding="utf-8"))))
    cards = list(apinav.parse_cards(nuxt_payload((F / "apinav_cards.html").read_text(encoding="utf-8"))))
    assert len(sites) >= 10 and all(s.category == "api-relay" for s in sites)
    assert sites[0].extra.get("models")
    assert len(cards) >= 20 and all(c.price is not None for c in cards)

def test_ldxp_showcase_json():
    o = list(ldxp_showcase.parse(json.loads((F / "ldxp_showcase.json").read_text(encoding="utf-8"))))
    assert len(o) == 20 and o[0].seller and o[0].url

def test_oai9_loose_mapping():
    o = list(oai9.parse({"items": [{"title": "Gemini Pro 18个月", "minPrice": 9.9, "stock": 3, "shop": "x", "sales24h": 12}]}))
    assert o[0].price == 9.9 and o[0].category in ("account","gcp-trial","gemini") and o[0].extra["sales_24h"] == 12

def test_disabled_by_default():
    ids = {a.id: getattr(a, "enabled", True) for a in ALL}
    assert ids["ldxp-merchant"] is False and ids["oai9"] is False
    o = list(ldxp_merchant.parse({"data": {"list": [{"goods_name": "Claude Pro", "price": 99, "stock": 2}]}}))
    assert o[0].category in ("account","claude","topup")
