from typing import Iterable, Protocol
from ..schema import Offer

class Adapter(Protocol):
    id: str
    def fetch(self) -> Iterable[Offer]: ...
