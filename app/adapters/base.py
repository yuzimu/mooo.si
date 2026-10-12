from typing import Iterable, Protocol
from ..schema import Offer

class Adapter(Protocol):
    id: str
    use_proxy: bool      # 是否走代理池
    use_browser: bool    # 是否需要指纹浏览器（CDP）
    def fetch(self) -> Iterable[Offer]: ...
