from .. import config
from .priceai import PriceAI
from .aigood import AIGood
from .apinav import ApiNav
from .ldxp_showcase import LdxpShowcase
from .oai9 import Oai9Hot
from .ldxp_merchant import LdxpMerchant

ALL = [PriceAI(), AIGood(), ApiNav(), LdxpShowcase(), Oai9Hot(), LdxpMerchant()]

def _enabled(a):
    if config.ENABLED_ADAPTERS: return a.id in config.ENABLED_ADAPTERS
    return getattr(a, "enabled", True)

REGISTRY = {a.id: a for a in ALL if _enabled(a)}
