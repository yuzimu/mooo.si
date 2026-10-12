"""GitHub awesome / 导航类列表：读取配置的 raw Markdown，提取外链。"""
import re
from .. import config
from ..net import client
from .telegram import hint_for

MD_LINK = re.compile(r"\[([^\]]{1,80})\]\((https?://[^)\s]+)\)")

class GitHubLists:
    id, enabled, min_interval_h = "github-lists", True, 24
    def discover(self):
        with client() as c:
            for u in config.GITHUB_LIST_URLS:
                r = c.get(u)
                if r.status_code != 200: continue
                for line in r.text.splitlines():
                    for label, link in MD_LINK.findall(line):
                        yield link, hint_for(line), f"{u.split('/')[4]}: {label}", None
