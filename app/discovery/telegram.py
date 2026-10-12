"""Telegram：① 用户的 tg-collector messages.db（只读，immutable 打开，绝不写入）；② 公开频道预览 t.me/s/<name>。"""
import re, sqlite3, os
from .. import config, store
from ..net import client
from ..adapters._util import polite_sleep

URL_RE = re.compile(r"https?://[^\s<>\"'）)\]】，。、]+|(?<![\w.@/])t\.me/[\w+/-]+|(?<![\w/.@])(?:[a-z0-9-]+\.)+"
                    r"(?:com|cn|cc|net|org|io|ai|top|xyz|site|shop|vip|me|app|dev|pro|chat|store|link|club|fun|ltd|win|one|tech|so|gg)"
                    r"(?:/[^\s<>\"'）)\]】，。、]*)?", re.I)
RELAY_HINT = re.compile(r"中转|api|key|令牌|倍率|new-?api|one-?api|claude code|codex", re.I)
SHOP_HINT = re.compile(r"卡网|小铺|店铺|发卡|自动发货|成品号|接码|代充", re.I)

def hint_for(text):
    if SHOP_HINT.search(text or ""): return "card_shop"
    if RELAY_HINT.search(text or ""): return "relay"
    return None

def extract(text):
    for u in URL_RE.findall(text or ""):
        yield u

class TelegramDB:
    id = "tg-collector"
    @property
    def enabled(self): return bool(config.TG_DB_PATH) and os.path.exists(config.TG_DB_PATH)
    def discover(self):
        con = sqlite3.connect(f"file:{config.TG_DB_PATH}?mode=ro&immutable=1", uri=True)
        try:
            for title, uname, date, text in con.execute("select chat_title, chat_username, date, text from msgs"):
                h = hint_for(text)
                for u in extract(text):
                    yield u, ("tg" if "t.me/" in u else h), f"[{title}] {(text or '')[:200]}", date
                if uname: yield f"https://t.me/{uname}", "tg", title or "", date
        finally:
            con.close()

class TelegramPreview:
    """对已发现的 TG 公开频道抓 t.me/s/<name> 预览页（群组会 302，跳过），从最近消息里继续发现链接。"""
    id, enabled, min_interval_h = "tg-preview", True, 24
    def discover(self):
        names = [d["_id"][3:] for d in store.db().targets.find({"type": "tg"}, {"_id": 1}).sort("mentions", -1).limit(config.TG_PREVIEW_MAX)]
        with client(headers={"User-Agent": config.BROWSER_UA}) as c:
            for n in names:
                r = c.get(f"https://t.me/s/{n}", follow_redirects=False)
                store.db().targets.update_one({"_id": f"tg:{n}"}, {"$set": {"tg_public": r.status_code == 200}})
                if r.status_code != 200: continue
                for m in re.findall(r'href="(https?://[^"]+)"', r.text):
                    if "t.me/" in m and f"/{n}/" in m: continue
                    yield m, hint_for(m), f"t.me/s/{n}", None
                polite_sleep()
