"""Telegram 报价适配器接口（仅设计，不连接 oracle 上的 /opt/tg-collector）。
预期由采集器侧只读导出 JSONL：{chat, msg_id, date, text}，本适配器读取本地导出文件并解析报价。"""
import json, re
from ..schema import Offer, guess_category
PRICE = re.compile(r"(\d+(?:\.\d+)?)\s*(元|r|rmb|u|usdt|\$)", re.I)

class TelegramExport:
    id = "telegram"
    def __init__(self, path): self.path = path
    def fetch(self):
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                m = json.loads(line); t = m.get("text", ""); pm = PRICE.search(t)
                if not pm: continue
                cur = "USD" if pm.group(2).lower() in ("u", "usdt", "$") else "CNY"
                yield Offer(source="telegram", product=t[:40], category=guess_category(t),
                            title=t[:200], price=float(pm.group(1)), currency=cur,
                            seller=m.get("chat"), captured_at=m.get("date"))
