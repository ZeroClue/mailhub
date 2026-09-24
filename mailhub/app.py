"""FastAPI REST API server for Mailhub."""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import signal
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .config import ConfigError, load_config
from .core import Core, CoreError, SendDenied


# Global core instance
_core: Optional[Core] = None


def _validate_host(host: str) -> str:
    """Validate that host is a loopback address (unless explicitly allowed)."""
    import os
    allow_non_loopback = os.getenv("MAILHUB_ALLOW_NON_LOOPBACK", "").lower() in ("1", "true", "yes")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_loopback and not allow_non_loopback:
            raise ValueError(f"host must be a loopback address, got {host}")
    except ValueError as e:
        if "must be a loopback" in str(e):
            raise
        raise ValueError(f"invalid host address: {host}") from e
    return host


def get_core() -> Optional[Core]:
    return _core


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _core
    try:
        from .config import load_config
        _core = Core(config=load_config())
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
    app = FastAPI(
        title="Mailhub",
        description="Local personal-operations hub for AI assistants",
        version="0.1.1",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        """Health check endpoint - returns basic status."""
        return {"status": "ok", "version": "0.1.2"}

    @app.get("/health/detailed")
    async def health_detailed():
        """Detailed health check - includes adapter status."""
        core = get_core()
        if core is None:
            return {"status": "degraded", "version": "0.1.2", "error": "Core not initialized"}
        
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
            "version": "0.1.2",
            "adapters": adapter_status
        }

    @app.get("/accounts", response_model=list[AccountStatus])
    async def list_accounts(scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        return [
            AccountStatus(
                alias=alias,
                provider=acc.provider,
                capabilities=acc.capabilities,
                email=acc.email,
            )
            for alias, acc in core.config.accounts.items()
        ]

    @app.get("/accounts/{alias}/folders")
    async def list_folders(alias: str, scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.folders(alias)
        except CoreError as e:
            raise HTTPException(404, str(e))

    @app.get("/accounts/{alias}/search")
    async def search_messages(
        alias: str,
        q: str,
        max_results: int = 50,
        page_token: str | None = None,
        scope: str = Depends(verify_token),
    ):
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.search(alias, q, max_results=max_results, page_token=page_token)
        except CoreError as e:
            raise HTTPException(400, str(e))

    @app.get("/accounts/{alias}/messages/{message_id}")
    async def get_message(alias: str, message_id: str, scope: str = Depends(verify_token)):
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.get(alias, message_id)
        except CoreError as e:
            raise HTTPException(404, str(e))

    @app.post("/accounts/{alias}/messages")
    async def send_message(
        alias: str,
        msg: SendRequest,
        scope: str = Depends(verify_token),
    ):
        if scope != "full":
            raise HTTPException(403, "full scope required for sending")
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.send(
                alias,
                to=msg.to,
                cc=msg.cc,
                bcc=msg.bcc,
                subject=msg.subject,
                text_body=msg.text_body,
                html_body=msg.html_body,
                in_reply_to=msg.in_reply_to,
                references=msg.references,
                confirm=True,
            )
        except CoreError as e:
            raise HTTPException(400, str(e))

    @app.post("/accounts/{alias}/drafts")
    async def create_draft(
        alias: str,
        msg: DraftRequest,
        scope: str = Depends(verify_token),
    ):
        if scope != "full":
            raise HTTPException(403, "full scope required for drafts")
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.draft(
                alias,
                to=msg.to,
                cc=msg.cc,
                bcc=msg.bcc,
                subject=msg.subject,
                text_body=msg.text_body,
                html_body=msg.html_body,
                in_reply_to=msg.in_reply_to,
                references=msg.references,
            )
        except CoreError as e:
            raise HTTPException(400, str(e))

    @app.post("/accounts/{alias}/messages/{message_id}/move")
    async def move_message(
        alias: str,
        message_id: str,
        req: MoveRequest,
        scope: str = Depends(verify_token),
    ):
        if scope != "full":
            raise HTTPException(403, "full scope required for move")
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.move(alias, message_id, req.destination)
        except CoreError as e:
            raise HTTPException(400, str(e))

    @app.post("/accounts/{alias}/messages/{message_id}/trash")
    async def trash_message(
        alias: str,
        message_id: str,
        scope: str = Depends(verify_token),
    ):
        if scope != "full":
            raise HTTPException(403, "full scope required for trash")
        core = get_core()
        if core is None:
            raise HTTPException(503, "Core not initialized")
        try:
            return core.trash(alias, message_id)
        except CoreError as e:
            raise HTTPException(400, str(e))

    return app


class AccountStatus(BaseModel):
    alias: str
    provider: str
    capabilities: list[str]
    email: str


class SendRequest(BaseModel):
    to: list[str]
    cc: list[str] = []
    bcc: list[str] = []
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    in_reply_to: str | None = None
    references: list[str] = []


class DraftRequest(BaseModel):
    to: list[str]
    cc: list[str] = []
    bcc: list[str] = []
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    in_reply_to: str | None = None
    references: list[str] = []


class MoveRequest(BaseModel):
    destination: str


async def verify_token(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> str:
    """Verify bearer token or API key."""
    from .config import load_config
    
    config = load_config()
    auth = config.auth
    
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_api_key:
        token = x_api_key
    
    if not token:
        raise HTTPException(401, "Missing authorization")
    
    if token == auth.full_token:
        return "full"
    elif token == auth.ro_token:
        return "ro"
    else:
        raise HTTPException(401, "Invalid token")


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
