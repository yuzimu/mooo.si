from . import store
from .adapters import REGISTRY

def run_adapter(adapter):
    try:
        offers = [o.to_dict() for o in adapter.fetch()]
        return store.save_run(adapter.id, offers, raw=getattr(adapter, "raw", None))
    except Exception as e:  # noqa: BLE001
        return store.save_run(adapter.id, [], error=repr(e)[:2000])

def run_all():
    return [run_adapter(a) for a in REGISTRY.values()]

if __name__ == "__main__":
    store.ensure_indexes()
    for r in run_all(): print(r.source, r.count, r.error)
