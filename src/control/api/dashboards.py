"""Dashboards (ADR 0009): named screens the user arranges, the same on every browser.

The Engine only keeps them: the UI reads each item's Device or Group through the usual endpoints.
Anyone who may use the Engine may change them. Changes are whole: the latest one wins.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..engine import dashboards
from ..engine.registry import Dashboard, Registry
from .deps import registry

router = APIRouter(prefix="/api/dashboards")


class ItemIO(BaseModel):
    id: str | None = Field(None, description="kept across changes; left out, the Engine makes one")
    kind: str = Field(description="tile, heading or spacer")
    size: str | None = Field(None, description='"WxH" in grid cells, or "full"; left out, the kind\'s default')
    target: str | None = Field(None, description="a Tile's Device or Group uid")
    text: str | None = Field(None, description="a Heading's text")


class DashboardOut(BaseModel):
    uid: str
    name: str
    items: list[ItemIO]


def _out(d: Dashboard) -> DashboardOut:
    return DashboardOut(uid=d.uid, name=d.name, items=[ItemIO(**i) for i in d.items])


def _name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("a dashboard needs a name")
    return name


def _items(r: Registry, items: list[ItemIO]) -> list[dict]:
    return dashboards.check_items([i.model_dump(exclude_none=True) for i in items], r.targets())


@router.get("", response_model=list[DashboardOut])
def list_dashboards(r: Registry = Depends(registry)):
    return [_out(d) for d in r.dashboards()]


class DashboardIn(BaseModel):
    name: str
    items: list[ItemIO] = []


@router.post("", response_model=DashboardOut, status_code=201)
def add_dashboard(body: DashboardIn, r: Registry = Depends(registry)):
    uid = r.add_dashboard(_name(body.name), _items(r, body.items))
    return _out(r.get_dashboard(uid))


class OrderIn(BaseModel):
    uids: list[str]


@router.put("/order", response_model=list[DashboardOut])
def order_dashboards(body: OrderIn, r: Registry = Depends(registry)):
    r.order_dashboards(body.uids)
    return [_out(d) for d in r.dashboards()]


@router.get("/{uid}", response_model=DashboardOut)
def get_dashboard(uid: str, r: Registry = Depends(registry)):
    return _out(r.get_dashboard(uid))


class DashboardPatch(BaseModel):
    name: str | None = None
    items: list[ItemIO] | None = Field(None, description="the full new list, in order")


@router.patch("/{uid}", response_model=DashboardOut)
def patch_dashboard(uid: str, patch: DashboardPatch, r: Registry = Depends(registry)):
    r.get_dashboard(uid)  # 404s early
    name = _name(patch.name) if patch.name is not None else None
    items = _items(r, patch.items) if patch.items is not None else None
    r.update_dashboard(uid, name=name, items=items)
    return _out(r.get_dashboard(uid))


@router.delete("/{uid}", status_code=204)
def forget_dashboard(uid: str, r: Registry = Depends(registry)):
    r.forget_dashboard(uid)
