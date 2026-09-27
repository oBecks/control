"""Dashboards (ADR 0010): named screens the user arranges, the same on every browser.

The Engine only keeps them: the UI reads each item's Device or Group through the usual endpoints,
and arranges the items itself (pushing others down on a drop). Anyone who may use the Engine may
change them. Changes are whole: the latest one wins.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..engine import dashboards
from ..engine.registry import Dashboard, Registry
from .deps import registry

router = APIRouter(prefix="/api/dashboards")


class ItemIO(BaseModel):
    id: str | None = Field(None, description="kept across changes; left out, the Engine makes one")
    kind: str = Field(description="tile, heading, big_control, pad (a Remote Pad), button (a Single Button), clock or run (a Run Button)")
    x: int = Field(description="its column, from 0")
    y: int = Field(description="its row, from 0; a row is half a Tile tall")
    w: int | None = Field(None, description="its width in columns; left out, the kind's default")
    h: int | None = Field(None, description="its height in rows (a Tile at least 2); left out, the kind's default")
    target: str | None = Field(None, description="a Tile's, Big Control's, Remote Pad's or button's Device or Group uid; a Run Button's Automation uid")
    control: str | None = Field(None, description="a Big Control's: brightness, colour or climate")
    button: str | None = Field(None, description="a button's remote button, e.g. power or input:hdmi1")
    app: str | None = Field(None, description="a button's Streamer app, by package")
    text: str | None = Field(None, description="a Heading's text")
    align: str | None = Field(None, description="a Heading's: start, center or end")
    text_size: str | None = Field(None, description="a Heading's: s, m, l or xl")
    bold: bool | None = Field(None, description="a Heading's")


class DashboardOut(BaseModel):
    uid: str
    name: str
    columns: int
    items: list[ItemIO]


def _out(d: Dashboard) -> DashboardOut:
    return DashboardOut(uid=d.uid, name=d.name, columns=d.columns, items=[ItemIO(**i) for i in d.items])


def _name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("a dashboard needs a name")
    return name


def _items(r: Registry, items: list[ItemIO], columns: int) -> list[dict]:
    return dashboards.check_items([i.model_dump(exclude_none=True) for i in items], r.targets(), columns,
                                  r.automation_uids())


@router.get("", response_model=list[DashboardOut])
def list_dashboards(r: Registry = Depends(registry)):
    return [_out(d) for d in r.dashboards()]


class DashboardIn(BaseModel):
    name: str
    columns: int = Field(8, description="4 for a phone, 6 for a tablet, 8 for a desktop")
    items: list[ItemIO] = []


@router.post("", response_model=DashboardOut, status_code=201)
def add_dashboard(body: DashboardIn, r: Registry = Depends(registry)):
    columns = dashboards.check_columns(body.columns)
    uid = r.add_dashboard(_name(body.name), columns, _items(r, body.items, columns))
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
    columns: int | None = Field(None, description="send the items too when they must move to fit")
    items: list[ItemIO] | None = Field(None, description="the full new list")


@router.patch("/{uid}", response_model=DashboardOut)
def patch_dashboard(uid: str, patch: DashboardPatch, r: Registry = Depends(registry)):
    current = r.get_dashboard(uid)  # 404s early
    name = _name(patch.name) if patch.name is not None else None
    columns = dashboards.check_columns(patch.columns) if patch.columns is not None else None
    width = columns or current.columns
    if patch.items is not None:
        items = _items(r, patch.items, width)
    elif columns is not None:
        items = dashboards.check_items(current.items, r.targets(), width, r.automation_uids())  # still fits?
    else:
        items = None
    r.update_dashboard(uid, name=name, columns=columns, items=items)
    return _out(r.get_dashboard(uid))


@router.delete("/{uid}", status_code=204)
def forget_dashboard(uid: str, r: Registry = Depends(registry)):
    r.forget_dashboard(uid)
