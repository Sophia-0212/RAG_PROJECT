from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST

from rag_service.api_models import (
    ConversationResponse,
    DifyRagRequest,
    DifyRagResponse,
    ErrorResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)
from rag_service.application import ApplicationRuntime, create_runtime
from rag_service.auth import (
    AuthenticationError,
    GatewaySharedSecretIdentityProvider,
    IdentityClaims,
    IdentityProvider,
    TrustedHeaderIdentityProvider,
)
from rag_service.conversation import ConversationAccessError
from rag_service.resilience import CapacityExceededError, QuotaExceededError
from rag_service.service import RAGService, ServiceExecutionError, make_command
from rag_service.settings import get_settings


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_END = object()


def _error(code: str, message: str, request_id: str, status_code: int) -> JSONResponse:
    payload = {"error": {"code": code, "message": message, "request_id": request_id}}
    return JSONResponse(status_code=status_code, content=payload)


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _split_principals(values: list[str] | None) -> tuple[str, ...]:
    principals = []
    for value in values or []:
        principals.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(principals)


def _next(iterator: Iterator[dict[str, Any]]):
    try:
        return next(iterator)
    except StopIteration:
        return _END


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def create_app(
    *,
    runtime: ApplicationRuntime | None = None,
    service: RAGService | None = None,
    identity_provider: IdentityProvider | None = None,
) -> FastAPI:
    settings = get_settings()
    provider = identity_provider
    if provider is None and settings.gateway_shared_secret:
        provider = GatewaySharedSecretIdentityProvider(settings.gateway_shared_secret)
    if provider is None:
        provider = TrustedHeaderIdentityProvider(
            enabled=settings.environment in {"development", "dev", "test", "testing"},
        )
    identity_provider_configured = not isinstance(provider, TrustedHeaderIdentityProvider) or provider.enabled
    owns_runtime = runtime is None and service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.validate_service_startup(
            identity_provider_configured=identity_provider_configured,
        )
        active_runtime = runtime
        active_service = service
        if active_service is None:
            active_runtime = active_runtime or create_runtime(settings=settings)
            active_service = RAGService(active_runtime)
        app.state.rag_service = active_service
        try:
            yield
        finally:
            if owns_runtime and active_runtime is not None:
                active_runtime.close()

    app = FastAPI(
        title="RAG Enterprise Service",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID")
        if supplied and not _REQUEST_ID_PATTERN.fullmatch(supplied):
            generated = str(uuid4())
            response = _error(
                "INVALID_REQUEST_ID",
                "X-Request-ID contains unsupported characters or is too long",
                generated,
                400,
            )
            response.headers["X-Request-ID"] = generated
            return response
        request.state.request_id = supplied or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AuthenticationError)
    async def authentication_error(request: Request, exc: AuthenticationError):
        return _error("AUTHENTICATION_FAILED", str(exc), _request_id(request), 401)

    @app.exception_handler(ConversationAccessError)
    async def conversation_access_error(request: Request, exc: ConversationAccessError):
        return _error("CONVERSATION_FORBIDDEN", str(exc), _request_id(request), 403)

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError):
        return _error("CONVERSATION_NOT_FOUND", "conversation does not exist", _request_id(request), 404)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return _error("VALIDATION_ERROR", "request validation failed", _request_id(request), 422)

    @app.exception_handler(ServiceExecutionError)
    async def service_error(request: Request, exc: ServiceExecutionError):
        return _error(
            "DEPENDENCY_UNAVAILABLE",
            "RAG workflow is temporarily unavailable",
            _request_id(request),
            503,
        )

    @app.exception_handler(QuotaExceededError)
    async def quota_error(request: Request, exc: QuotaExceededError):
        response = _error("TENANT_QUOTA_EXCEEDED", "tenant request quota exceeded", _request_id(request), 429)
        response.headers["Retry-After"] = "1"
        return response

    @app.exception_handler(CapacityExceededError)
    async def capacity_error(request: Request, exc: CapacityExceededError):
        response = _error("SERVICE_BUSY", "service concurrency capacity exceeded", _request_id(request), 503)
        response.headers["Retry-After"] = "1"
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return _error("INTERNAL_ERROR", "an unexpected internal error occurred", _request_id(request), 500)

    async def identity(
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
        x_user_id: str | None = Header(default=None, alias="X-User-ID"),
        x_principal_id: list[str] | None = Header(default=None, alias="X-Principal-ID"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> IdentityClaims:
        return provider.verify(
            tenant_id=x_tenant_id,
            user_id=x_user_id,
            principal_ids=_split_principals(x_principal_id),
            authorization=authorization,
        )

    def active_service(request: Request) -> RAGService:
        return request.app.state.rag_service

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": "ok"})

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready(request: Request) -> Response:
        rag_service = active_service(request)
        identity_ready = identity_provider_configured
        store_ready = await run_in_threadpool(rag_service.ready)
        healthy = store_ready and identity_ready
        payload = HealthResponse(
            status="ok" if healthy else "not_ready",
            checks={
                "conversation_store": "ok" if store_ready else "failed",
                "identity_provider": "ok" if identity_ready else "missing",
            },
        )
        return JSONResponse(
            status_code=200 if healthy else 503,
            content=payload.model_dump(mode="json"),
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        payload = await run_in_threadpool(active_service(request).metrics)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/query", response_model=QueryResponse, tags=["query"])
    async def query(
        body: QueryRequest,
        request: Request,
        claims: IdentityClaims = Depends(identity),
    ) -> QueryResponse:
        command = make_command(
            question=body.question,
            conversation_id=body.conversation_id,
            request_id=_request_id(request),
            constraints=body.constraints.model_dump(mode="python"),
        )
        result = await run_in_threadpool(active_service(request).query, command, claims)
        return QueryResponse.model_validate(result)

    @app.post("/v1/query/stream", tags=["query"])
    async def stream_query(
        body: QueryRequest,
        request: Request,
        claims: IdentityClaims = Depends(identity),
    ) -> StreamingResponse:
        command = make_command(
            question=body.question,
            conversation_id=body.conversation_id,
            request_id=_request_id(request),
            constraints=body.constraints.model_dump(mode="python"),
        )
        iterator = active_service(request).stream(command, claims)

        async def events() -> AsyncIterator[str]:
            try:
                while not await request.is_disconnected():
                    item = await run_in_threadpool(_next, iterator)
                    if item is _END:
                        yield _sse("done", {"request_id": command.request_id})
                        break
                    yield _sse(str(item["type"]), item)
            except Exception:
                yield _sse(
                    "error",
                    {
                        "code": "STREAM_FAILED",
                        "message": "stream processing failed",
                        "request_id": command.request_id,
                    },
                )
            finally:
                close = getattr(iterator, "close", None)
                if close is not None:
                    await run_in_threadpool(close)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/conversations/{conversation_id}", response_model=ConversationResponse, tags=["conversation"])
    async def get_conversation(
        conversation_id: str,
        request: Request,
        claims: IdentityClaims = Depends(identity),
    ) -> ConversationResponse:
        record = await run_in_threadpool(
            active_service(request).get_conversation,
            conversation_id,
            claims,
        )
        return ConversationResponse(
            conversation_id=record.conversation_id,
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            updated_at_ms=record.updated_at_ms,
            expires_at_ms=record.expires_at_ms,
        )

    @app.delete("/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["conversation"])
    async def delete_conversation(
        conversation_id: str,
        request: Request,
        claims: IdentityClaims = Depends(identity),
    ) -> Response:
        deleted = await run_in_threadpool(
            active_service(request).delete_conversation,
            conversation_id,
            claims,
        )
        if not deleted:
            raise KeyError("conversation does not exist")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/integrations/dify/v1/query", response_model=DifyRagResponse, tags=["integration"])
    async def dify_query(
        body: DifyRagRequest,
        request: Request,
        claims: IdentityClaims = Depends(identity),
    ) -> DifyRagResponse:
        constraints = {
            "source_ids": body.inputs.get("source_ids", []),
            "version_ids": body.inputs.get("version_ids", []),
        }
        command = make_command(
            question=body.query,
            conversation_id=body.conversation_id,
            request_id=_request_id(request),
            constraints=constraints,
        )
        result = await run_in_threadpool(active_service(request).query, command, claims)
        return DifyRagResponse(
            answer=result["answer"],
            conversation_id=result["conversation_id"],
            metadata={
                "request_id": result["request_id"],
                "citations": result["citations"],
                "refusal_reason": result["refusal_reason"],
                "degraded": result["degraded"],
            },
        )

    return app
