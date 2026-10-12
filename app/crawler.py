from sqlalchemy import delete
from .db import OfferRow, CrawlRun, Session
from .adapters import REGISTRY

def run_adapter(adapter, session_factory=Session):
    with session_factory() as s:
        run = CrawlRun(source=adapter.id)
        try:
            offers = list(adapter.fetch())
            s.execute(delete(OfferRow).where(OfferRow.source == adapter.id))  # 当前快照替换
            s.add_all(OfferRow(**o.to_dict()) for o in offers)
            run.count = len(offers)
        except Exception as e:  # noqa: BLE001
            s.rollback(); run.error = repr(e)[:2000]
        s.add(run); s.commit()
        return run

def run_all(session_factory=Session):
    return [run_adapter(a, session_factory) for a in REGISTRY.values()]

if __name__ == "__main__":
    from .db import Base, engine
    Base.metadata.create_all(engine)
    for r in run_all(): print(r.source, r.count, r.error)
