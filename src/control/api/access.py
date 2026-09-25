"""Who may use the Engine (ADR 0003). This machine is trusted by address. Every other browser must be
an Approved Browser: it asks with a short code, and the user approves the code here or from another
Approved Browser. The browser then holds a long random token in a cookie; the Registry keeps its hash."""

import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..engine.registry import Registry
from . import lan
from .deps import registry

COOKIE = "control_browser"
PHONE_ACCESS = "phone_access"  # setting: bool
REQUEST_TTL = 10 * 60
MAX_PENDING = 10

_LOOPBACK = {"127.0.0.1", "::1"}
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}

router = APIRouter(prefix="/api/access")


# --- The gate --------------------------------------------------------------


def _allowed_hosts() -> set[str]:
    return _LOCAL_NAMES | ({lan.listener.ip} if lan.listener.ip else set())


def _is_public(request: Request) -> bool:
    """What an unapproved browser may do: load the UI and ask for access, nothing else."""
    path = request.url.path
    if path == "/api/access/me" or path.startswith("/api/access/claims/"):
        return True
    if path == "/api/access/requests":
        return request.method == "POST"  # asking, not listing who else is asking
    return not (path.startswith("/api/") or path in ("/docs", "/redoc", "/openapi.json"))


def _deny(status: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code})


async def gate(request: Request, call_next):
    # A Host that isn't us means DNS rebinding: a website pointing its own name at this machine.
    if request.url.hostname not in _allowed_hosts():
        return _deny(400, "Unknown host", "bad_host")
    # A request some other website's page sent (e.g. a form posting to 127.0.0.1).
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).hostname not in _allowed_hosts():
        return _deny(403, "Requests from other websites aren't allowed", "bad_origin")

    request.state.local = bool(request.client and request.client.host in _LOOPBACK)
    request.state.browser = None
    if not request.state.local:
        r = Registry()
        try:
            if not r.setting(PHONE_ACCESS, False):
                return _deny(403, "Phone access is turned off on the computer running Control", "phone_access_off")
            token = request.cookies.get(COOKIE)
            browser = r.browser_for_token(token) if token else None
            if browser and time.time() - browser.last_seen > 60:
                r.browser_seen(browser.id)
        finally:
            r.close()
        request.state.browser = browser
        if browser is None and not _is_public(request):
            return _deny(401, "This browser isn't approved yet", "approval_required")
    return await call_next(request)


def _trusted(request: Request) -> bool:
    return request.state.local or request.state.browser is not None


# --- Asking for access -------------------------------------------------------


@dataclass
class _Ask:
    ref: str  # what approvers refer to it by
    claim: str  # secret: only the asking browser knows it, and trades it for the token
    code: str
    name: str
    client: str
    created: float
    status: str = "pending"  # pending | approved | denied


_asks: dict[str, _Ask] = {}
_lock = threading.Lock()


def _prune() -> None:
    now = time.time()
    for ref in [ref for ref, a in _asks.items() if now - a.created > REQUEST_TTL]:
        del _asks[ref]


def browser_name(ua: str) -> str:
    """A name the user recognises in the approval banner and the Approved Browsers list."""
    device = next(
        (name for key, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                ("Windows", "Windows"), ("Macintosh", "Mac"), ("Linux", "Linux")) if key in ua),
        "Browser",
    )
    browser = next(
        (name for key, name in (("SamsungBrowser", "Samsung Internet"), ("EdgA", "Edge"), ("Edg/", "Edge"),
                                ("FxiOS", "Firefox"), ("Firefox", "Firefox"), ("CriOS", "Chrome"),
                                ("Chrome", "Chrome"), ("Safari", "Safari")) if key in ua),
        None,
    )
    if browser is None and device in ("iPhone", "iPad"):
        browser = "Home Screen app"  # iOS home-screen apps drop "Safari" from the user agent
    return f"{device} · {browser}" if browser else device


class AccessOut(BaseModel):
    access: str  # local | approved | none
    browser_id: str | None = None


@router.get("/me", response_model=AccessOut)
def me(request: Request):
    if request.state.local:
        return AccessOut(access="local")
    b = request.state.browser
    return AccessOut(access="approved", browser_id=b.id) if b else AccessOut(access="none")


@router.post("/requests")
def ask(request: Request):
    """An unapproved browser asks for access; it shows `code` and polls `/claims/{claim}`."""
    if _trusted(request):
        raise HTTPException(409, "This browser already has access")
    client = request.client.host if request.client else ""
    with _lock:
        _prune()
        for ref in [ref for ref, a in _asks.items() if a.client == client and a.status == "pending"]:
            del _asks[ref]  # asking again replaces this device's earlier code
        if sum(a.status == "pending" for a in _asks.values()) >= MAX_PENDING:
            raise HTTPException(429, "Too many devices are waiting. Approve or deny them first.")
        a = _Ask(ref=secrets.token_hex(6), claim=secrets.token_urlsafe(24), code=f"{secrets.randbelow(10**6):06d}",
                 name=browser_name(request.headers.get("user-agent", "")), client=client, created=time.time())
        _asks[a.ref] = a
    return {"claim": a.claim, "code": a.code}


@router.get("/claims/{claim}")
def claim(claim: str, response: Response, r: Registry = Depends(registry)):
    """Poll while waiting. Once approved, this answer carries the browser's token, once."""
    with _lock:
        _prune()
        a = next((a for a in _asks.values() if secrets.compare_digest(a.claim, claim)), None)
        if a is None:
            return {"status": "expired"}
        if a.status == "pending":
            return {"status": "pending"}
        del _asks[a.ref]
    if a.status == "denied":
        return {"status": "denied"}
    token = secrets.token_urlsafe(32)
    r.approve_browser(token, a.name)
    response.set_cookie(COOKIE, token, max_age=10 * 365 * 24 * 3600, httponly=True, samesite="strict", path="/")
    return {"status": "approved"}


@router.get("/requests")
def pending():
    with _lock:
        _prune()
        return [{"ref": a.ref, "code": a.code, "name": a.name, "created": a.created}
                for a in sorted(_asks.values(), key=lambda a: a.created) if a.status == "pending"]


def _decide(ref: str, status: str) -> None:
    with _lock:
        _prune()
        a = _asks.get(ref)
        if a is None or a.status != "pending":
            raise LookupError("That request expired. Ask the phone to show a new code.")
        a.status = status


@router.post("/requests/{ref}/approve", status_code=204)
def approve(ref: str):
    _decide(ref, "approved")


@router.post("/requests/{ref}/deny", status_code=204)
def deny(ref: str):
    _decide(ref, "denied")


# --- Approved Browsers ---------------------------------------------------------


@router.get("/browsers")
def browsers(request: Request, r: Registry = Depends(registry)):
    current = request.state.browser.id if request.state.browser else None
    return [{"id": b.id, "name": b.name, "approved_at": b.approved_at, "last_seen": b.last_seen,
             "current": b.id == current} for b in r.approved_browsers()]


@router.delete("/browsers/{browser_id}", status_code=204)
def revoke(browser_id: str, r: Registry = Depends(registry)):
    r.revoke_browser(browser_id)


# --- Phone access on/off ---------------------------------------------------------


class PhoneAccessOut(BaseModel):
    on: bool
    url: str | None  # what phones open, while the LAN listener runs
    error: str | None
    can_change: bool  # only on the machine running the Engine


class PhoneAccessIn(BaseModel):
    on: bool


def _phone_status(request: Request, r: Registry) -> PhoneAccessOut:
    return PhoneAccessOut(on=r.setting(PHONE_ACCESS, False), url=lan.listener.url, error=lan.listener.error,
                          can_change=request.state.local)


@router.get("/phone", response_model=PhoneAccessOut)
def phone_status(request: Request, r: Registry = Depends(registry)):
    return _phone_status(request, r)


@router.put("/phone", response_model=PhoneAccessOut)
def set_phone_access(body: PhoneAccessIn, request: Request, r: Registry = Depends(registry)):
    if not request.state.local:
        raise HTTPException(403, "Phone access can only be changed on the computer running Control")
    r.set_setting(PHONE_ACCESS, body.on)
    if body.on:
        lan.listener.start()
    else:
        lan.listener.stop()
        with _lock:
            _asks.clear()
    return _phone_status(request, r)
