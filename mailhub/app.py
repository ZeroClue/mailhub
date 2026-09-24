"""FastAPI REST server for Mailhub (binds to 127.0.0.1 only)."""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import signal
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import ConfigError, load_config
from .core import Core, CoreError, SendDenied, RetryPolicy, SendPolicy
from .store import CredentialStore, state_path


def _validate_host(host: str) -> str:
    """Validate that host is a loopback address."""
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_loopback:
            raise ValueError(f"host must be a loopback address, got {host}")
    except ValueError as e:
        if "must be a loopback" in str(e):
            raise
        raise ValueError(f"invalid host address: {host}") from e
    return host


# Request/Response models
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class AccountStatus(BaseModel):
    alias: str
    provider: str
    email: str
    has_refresh_token: bool
    has_access_token: bool


class DoctorResponse(BaseModel):
    alias: str
    provider: str
    status: str
    profile: dict[str, Any] | None = None
    hint: str | None = None
    detail: str | None = None


class SearchRequest(BaseModel):
    query: str
    max_results: int = 50
    page_token: str | None = None


class MessageResponse(BaseModel):
    id: str
    thread_id: str | None = None
    label_ids: list[str] | None = None
    from_: dict[str, str] = Field(alias="from")
    to: list[dict[str, str]]
    cc: list[dict[str, str]] = []
    subject: str
    date: str
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[dict[str, Any]] = []
    has_attachments: bool = False


class SendRequest(BaseModel):
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    in_reply_to: str | None = None
    references: list[str] | None = None
    confirm: bool = False


class SendResponse(BaseModel):
    id: str
    thread_id: str | None = None
    status: str | None = None


class DraftRequest(BaseModel):
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    in_reply_to: str | None = None
    references: list[str] | None = None


class DraftResponse(BaseModel):
    id: str


class MoveRequest(BaseModel):
    destination: str


class MoveResponse(BaseModel):
    id: str
    label_ids: list[str] | None = None
    folder: str | None = None


class TrashResponse(BaseModel):
    id: str


class FoldersResponse(BaseModel):
    folders: list[dict[str, Any]]


class DoctorRequest(BaseModel):
    pass


# Global core instance
_core: Core | None = None


def get_core() -> Core:
    global _core
    if _core is None:
        raise HTTPException(status_code=500, detail="Core not initialized")
    return _core


def verify_token(authorization: str = Header(...)) -> str:
    """Verify bearer token and return scope (ro or full)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Invalid authorization header")
    token = authorization[7:]
    
    core = get_core()
    cfg = core._config
    auth_cfg = core._store.load().get("auth", {})
    ro_token = auth_cfg.get("ro_token", "")
    full_token = auth_cfg.get("full_token", "")
    
    if full_token and hmac.compare_digest(token, full_token):
        return "full"
    elif ro_token and hmac.compare_digest(token, ro_token):
        return "ro"
    else:
        raise HTTPException(status_code=403, detail="Invalid or missing bearer token")


def require_full_scope(scope: str = Depends(verify_token)) -> str:
    if scope != "full":
        raise HTTPException(status_code=403, detail="Full scope required")
    return scope


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _core
    try:
        config = load_config()
        _core = Core(config=config)
    except ConfigError:
        _core = None
    yield
    # Graceful shutdown
    if _core:
        for adapter in _core._adapters.values():
            if hasattr(adapter, 'close'):
                adapter.close()
        # Give adapters time to flush/cleanup
        import asyncio
        await asyncio.sleep(0.5)


def create_app(config_file: Path | None = None) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="mailhub",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        """Health check endpoint - returns basic status."""
        return {"status": "ok", "version": "0.1.1"}

    @app.get("/health/detailed")
    async def health_detailed():
        """Detailed health check - includes adapter status."""
        core = get_core()
        if core is None:
            return {"status": "degraded", "version": "0.1.1", "error": "Core not initialized"}
        
        adapter_status = {}
        for name, adapter in core._adapters.items():
            try:
                # Quick health check on each adapter
                profile = adapter.profile("default") if hasattr(adapter, 'profile') else {}
                adapter_status[name] = {"status": "ok", "profile": profile}
            except Exception as e:
                adapter_status[name] = {"status": "error", "error": str(e)}
        
        all_ok = all(s.get("status") == "ok" for s in adapter_status.values())
        return {
            "status": "ok" if all_ok else "degraded",
            "version": "0.1.1",
            "adapters": adapter_status
        }

    @app.get("/accounts", response_model=list[AccountStatus])
    async def list_accounts(scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        return core.accounts_status()

    @app.get("/accounts/{alias}/folders", response_model=FoldersResponse)
    async def list_folders(alias: str, scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            folders = core.folders(alias)
            return FoldersResponse(folders=folders)
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/accounts/{alias}/messages", response_model=dict)
    async def search_messages(
        alias: str,
        query: str = "",
        max_results: int = 50,
        page_token: str | None = None,
        scope: str = Depends(verify_token),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            result = core.search(alias, query, max_results=max_results, page_token=page_token)
            return result
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/accounts/{alias}/messages/{message_id}", response_model=MessageResponse)
    async def get_message(alias: str, message_id: str, scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            msg = core.get(alias, message_id)
            return MessageResponse(**msg)
        except CoreError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/accounts/{alias}/send", response_model=SendResponse)
    async def send_message(
        alias: str,
        request: SendRequest,
        scope: str = Depends(require_full_scope),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            result = core.send(
                alias,
                to=request.to,
                cc=request.cc,
                bcc=request.bcc,
                subject=request.subject,
                text_body=request.text_body,
                html_body=request.html_body,
                in_reply_to=request.in_reply_to,
                references=request.references,
                confirm=request.confirm,
            )
            return SendResponse(**result)
        except SendDenied as e:
            raise HTTPException(status_code=403, detail=str(e))
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/accounts/{alias}/draft", response_model=DraftResponse)
    async def create_draft(
        alias: str,
        request: DraftRequest,
        scope: str = Depends(require_full_scope),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            result = core.draft(
                alias,
                to=request.to,
                cc=request.cc,
                bcc=request.bcc,
                subject=request.subject,
                text_body=request.text_body,
                html_body=request.html_body,
                in_reply_to=request.in_reply_to,
                references=request.references,
            )
            return DraftResponse(**result)
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/accounts/{alias}/messages/{message_id}/move", response_model=MoveResponse)
    async def move_message(
        alias: str,
        message_id: str,
        request: MoveRequest,
        scope: str = Depends(require_full_scope),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            result = core.move(alias, message_id, request.destination)
            return MoveResponse(**result)
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/accounts/{alias}/messages/{message_id}/trash", response_model=TrashResponse)
    async def trash_message(
        alias: str,
        message_id: str,
        scope: str = Depends(require_full_scope),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        try:
            result = core.trash(alias, message_id)
            return TrashResponse(**result)
        except CoreError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/doctor", response_model=list[DoctorResponse])
    async def doctor(scope: str = Depends(require_full_scope)):
        core = get_core()
        if core is None:
            raise HTTPException(status_code=500, detail="Not configured")
        return core.doctor()

    @app.exception_handler(CoreError)
    async def core_error_handler(request: Request, exc: CoreError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(SendDenied)
    async def send_denied_handler(request: Request, exc: SendDenied):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    return app


def run_server(config_file: Path | None = None, host: str = "127.0.0.1", port: int = 8787):
    """Run the FastAPI server with uvicorn."""
    import uvicorn
    import signal
    import asyncio
    
    # Validate host is loopback
    try:
        _validate_host(host)
    except ValueError as e:
        raise SystemExit(f"mailhub: {e}")
    
    app = create_app(config_file)
    
    # Graceful shutdown handler
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        shutdown_event.set()
    
    # Install signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal_handler)
    
    # Custom uvicorn server with graceful shutdown
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        lifespan="on"
    )
    server = uvicorn.Server(config)
    
    # Run with graceful shutdown
    async def run_with_shutdown():
        serve_task = asyncio.create_task(server.serve())
        await shutdown_event.wait()
        server.should_exit = True
        await serve_task
    
    asyncio.run(run_with_shutdown())


if __name__ == "__main__":
    run_server()
