"""Telegram 报价适配器（仅接口）：读取 tg-collector 只读导出的 JSONL {chat,msg_id,date,text}。
不直接连接 messages.db。"""
import json, re
from ..schema import Offer, guess_category
PRICE = re.compile(r"(\d+(?:\.\d+)?)\s*(元|r|rmb|u|usdt|\$)", re.I)

class TelegramExport:
    id, use_proxy, use_browser = "telegram", False, False
    def __init__(self, path): self.path = path
    def fetch(self):
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                m = json.loads(line)
                t = m.get("text", "")
                pm = PRICE.search(t)
                if not pm: continue
                cur = "USD" if pm.group(2).lower() in ("u", "usdt", "$") else "CNY"
                yield Offer(source="telegram", product=t[:40], category=guess_category(t),
                            title=t[:200], price=float(pm.group(1)), currency=cur,
                            seller=m.get("chat"), captured_at=m.get("date"))
