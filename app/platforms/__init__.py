"""阶段二：平台指纹识别 + 定向抓取。每个平台适配器：detect(target, probe) / crawl(target) -> (offers, meta)。"""
from .fingerprint import fingerprint
from .catfk import CatFK
from .ldxp import LdxpShop
from .newapi import NewAPI

CRAWLERS = {"catfk": CatFK(), "ldxp": LdxpShop(), "new-api": NewAPI(), "one-api": NewAPI()}
__all__ = ["fingerprint", "CRAWLERS"]
