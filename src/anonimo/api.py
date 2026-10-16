import hmac
from threading import BoundedSemaphore

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters import sanitize_request
from .config import Policy, StrictModel
from .detector import DetectionError
from .engine import Blocked, Engine


class TextInput(StrictModel):
    text: str = Field(max_length=200000)


class RequestInput(StrictModel):
    url: str = Field(max_length=8192)
    method: str = Field(default="POST", max_length=16)
    content_type: str = Field(max_length=256)
    body: str = Field(max_length=262144)


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        events, size = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            size += len(event.get("body", b""))
            if size > 1048576:
                return await JSONResponse({"detail": "body_limit_exceeded"}, status_code=413)(scope, receive, send)
            events.append(event)
            if not event.get("more_body", False):
                break
        iterator = iter(events)
        async def replay():
            return next(iterator, {"type": "http.disconnect"})
        await self.app(scope, replay, send)


def create_app(policy: Policy, token: str, detector=None) -> FastAPI:
    if len(token) < 32:
        raise ValueError("Service token must have at least 32 characters")
    app = FastAPI(title="Anonimo", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    engine = Engine(policy, detector)
    capacity = BoundedSemaphore(4)

    def authorize(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # FastAPI's default validation response echoes the input.
        return JSONResponse({"detail": "invalid_request"}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "rules_and_local_model" if policy.model.enabled else "rules_only",
                "model_connectivity": "not_checked" if policy.model.enabled else "disabled",
                "version": "0.1.0"}

    def run(operation):
        if not capacity.acquire(blocking=False):
            raise HTTPException(status_code=503, detail="busy")
        try:
            return operation()
        except (Blocked, DetectionError) as exc:
            return {"status": "blocked", "reason": str(exc), "body": None, "counts": {}}
        except Exception:
            # Do not include input, URLs, token, model response or traceback.
            return {"status": "blocked", "reason": "analysis_failed", "body": None, "counts": {}}
        finally:
            capacity.release()

    @app.post("/v1/sanitize-text", dependencies=[Depends(authorize)])
    def text(payload: TextInput):
        def operation():
            values, counts = engine.sanitize([payload.text])
            return {"status": "sanitized", "text": values[0], "counts": counts}
        return run(operation)

    @app.post("/v1/sanitize-request", dependencies=[Depends(authorize)])
    def request(payload: RequestInput):
        return run(lambda: sanitize_request(engine, **payload.model_dump()))

    return app
