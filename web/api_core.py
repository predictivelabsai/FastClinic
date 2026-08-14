"""Shared FastSME FastAPI primitives vendored into each product repository."""

import json
import os
import secrets
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, create_model
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


class ErrorDetail(BaseModel):
    """Machine-readable API error."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Consistent error response envelope."""

    error: ErrorDetail


class PaginationMeta(BaseModel):
    """Offset pagination metadata."""

    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """API health response."""

    status: str
    product: str
    version: str
    writes_enabled: bool
    database_backend: str
    database_ready: bool


@dataclass(frozen=True)
class Resource:
    """A public API resource backed by an allow-listed table."""

    slug: str
    table: str
    title: str
    description: str
    write_fields: tuple[str, ...] = ()
    required_write_fields: tuple[str, ...] = ()
    update_fields: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()
    primary_key: str | None = None
    soft_delete_field: str | None = None
    soft_delete_value: Any = 1


class DatabaseBackend:
    """Small SQLite/PostgreSQL adapter with strict identifier allow-lists."""

    def __init__(
        self,
        path: str | Path,
        resources: tuple[Resource, ...],
        initialize: Callable[[], None] | None = None,
    ) -> None:
        self.path = str(path)
        self.resources = {resource.slug: resource for resource in resources}
        if initialize:
            initialize()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.is_postgres:
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
            except ImportError as exc:  # pragma: no cover - deployment guard
                raise RuntimeError("PostgreSQL requires psycopg2") from exc
            schema = os.getenv("FASTCLINIC_DB_SCHEMA") or "fast_clinic"
            if not schema.replace("_", "a").isalnum() or schema[0].isdigit():
                raise RuntimeError("FASTCLINIC_DB_SCHEMA is not a valid SQL identifier")
            connection = psycopg2.connect(
                self.path,
                connect_timeout=10,
                cursor_factory=RealDictCursor,
                options=f"-c search_path={schema}",
            )
        else:
            connection = sqlite3.connect(self.path, timeout=15)
            connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @property
    def is_postgres(self) -> bool:
        return self.path.startswith(("postgres://", "postgresql://"))

    def ready(self) -> bool:
        try:
            with self.connection() as connection:
                return self._execute(connection, "SELECT 1").fetchone() is not None
        except Exception:
            return False

    def _execute(self, connection, sql: str, params: tuple | list = ()):
        if self.is_postgres:
            cursor = connection.cursor()
            cursor.execute(sql.replace("?", "%s"), params)
            return cursor
        return connection.execute(sql, params)

    def columns(self, resource: Resource) -> list[dict[str, Any]]:
        with self.connection() as connection:
            if self.is_postgres:
                rows = self._execute(
                    connection,
                    """SELECT column_name AS name,
                              data_type AS type,
                              CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END AS notnull,
                              column_default AS dflt_value,
                              CASE WHEN EXISTS (
                                  SELECT 1
                                  FROM information_schema.table_constraints tc
                                  JOIN information_schema.key_column_usage kcu
                                    ON tc.constraint_name=kcu.constraint_name
                                   AND tc.table_schema=kcu.table_schema
                                 WHERE tc.constraint_type='PRIMARY KEY'
                                   AND tc.table_schema=? AND tc.table_name=?
                                   AND kcu.column_name=c.column_name
                              ) THEN 1 ELSE 0 END AS pk
                       FROM information_schema.columns c
                       WHERE table_schema=? AND table_name=?
                       ORDER BY ordinal_position""",
                    (
                        os.getenv("FASTCLINIC_DB_SCHEMA") or "fast_clinic",
                        resource.table,
                        os.getenv("FASTCLINIC_DB_SCHEMA") or "fast_clinic",
                        resource.table,
                    ),
                ).fetchall()
            else:
                rows = self._execute(
                    connection, f'PRAGMA table_info("{resource.table}")'
                ).fetchall()
        if not rows:
            raise RuntimeError(
                f"API resource {resource.slug!r} references missing table "
                f"{resource.table!r}"
            )
        return [dict(row) for row in rows]

    def primary_key(self, resource: Resource) -> str:
        if resource.primary_key:
            return resource.primary_key
        columns = self.columns(resource)
        primary = next((column["name"] for column in columns if column["pk"]), None)
        return primary or columns[0]["name"]

    def list(
        self,
        resource: Resource,
        *,
        limit: int,
        offset: int,
        query: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ""
        params: list[Any] = []
        if query and resource.search_fields:
            operator = "ILIKE" if self.is_postgres else "LIKE"
            clauses = [
                f'CAST("{field}" AS TEXT) {operator} ?'
                for field in resource.search_fields
            ]
            where = " WHERE " + " OR ".join(clauses)
            params.extend([f"%{query}%"] * len(clauses))
        with self.connection() as connection:
            total_row = self._execute(
                connection,
                f'SELECT COUNT(*) FROM "{resource.table}"{where}', params
            ).fetchone()
            total = next(iter(dict(total_row).values()))
            rows = self._execute(
                connection,
                f'SELECT * FROM "{resource.table}"{where} '
                f'ORDER BY "{self.primary_key(resource)}" LIMIT ? OFFSET ?',
                (*params, limit, offset),
            ).fetchall()
        return [_serialise_row(row) for row in rows], total

    def get(self, resource: Resource, item_id: str) -> dict[str, Any] | None:
        primary_key = self.primary_key(resource)
        with self.connection() as connection:
            row = self._execute(
                connection,
                f'SELECT * FROM "{resource.table}" WHERE "{primary_key}"=?',
                (item_id,),
            ).fetchone()
        return _serialise_row(row) if row else None

    def create(self, resource: Resource, values: dict[str, Any]) -> dict[str, Any]:
        allowed = set(resource.write_fields)
        clean = {key: value for key, value in values.items() if key in allowed and value is not None}
        if not clean:
            raise ValueError("At least one writable field is required")
        columns = {column["name"]: column for column in self.columns(resource)}
        primary_key = self.primary_key(resource)
        if (
            primary_key not in clean
            and "TEXT" in (columns[primary_key]["type"] or "").upper()
        ):
            clean[primary_key] = uuid.uuid4().hex
        timestamp = datetime.now(UTC).isoformat()
        for field in ("created", "created_at", "modified", "updated_at"):
            column = columns.get(field)
            if column and field not in clean and column["dflt_value"] is None:
                clean[field] = timestamp
        fields = tuple(clean)
        placeholders = ",".join("?" for _ in fields)
        quoted = ",".join(f'"{field}"' for field in fields)
        with self.connection() as connection:
            statement = f'INSERT INTO "{resource.table}" ({quoted}) VALUES ({placeholders})'
            if self.is_postgres:
                statement += f' RETURNING "{primary_key}"'
            cursor = self._execute(connection, statement, tuple(clean[field] for field in fields))
            item_id = (
                cursor.fetchone()[primary_key]
                if self.is_postgres
                else cursor.lastrowid
            )
            connection.commit()
        created = self.get(resource, str(item_id))
        return created or clean

    def update(
        self,
        resource: Resource,
        item_id: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        before = self.get(resource, item_id)
        if before is None:
            return None
        allowed = set(resource.update_fields or resource.write_fields)
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            raise ValueError("At least one writable field is required")
        columns = {column["name"]: column for column in self.columns(resource)}
        timestamp = datetime.now(UTC).isoformat()
        for field in ("modified", "updated_at"):
            if field in columns and field not in clean:
                clean[field] = timestamp
        assignments = ",".join(f'"{field}"=?' for field in clean)
        primary_key = self.primary_key(resource)
        with self.connection() as connection:
            self._execute(
                connection,
                f'UPDATE "{resource.table}" SET {assignments} WHERE "{primary_key}"=?',
                (*clean.values(), item_id),
            )
            connection.commit()
        return before, self.get(resource, item_id) or before

    def delete(
        self,
        resource: Resource,
        item_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not resource.soft_delete_field:
            raise ValueError("This resource does not support deletion")
        before = self.get(resource, item_id)
        if before is None:
            return None
        value = resource.soft_delete_value
        if value == "__timestamp__":
            value = datetime.now(UTC).isoformat()
        primary_key = self.primary_key(resource)
        with self.connection() as connection:
            self._execute(
                connection,
                f'UPDATE "{resource.table}" SET "{resource.soft_delete_field}"=? '
                f'WHERE "{primary_key}"=?',
                (value, item_id),
            )
            connection.commit()
        return before, self.get(resource, item_id) or before


def _serialise_row(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, bytes):
            value = value.hex()
        result[key] = value
    return result


def _python_type(sql_type: str) -> type[Any]:
    normalized = (sql_type or "").upper()
    if "INT" in normalized:
        return int
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
        return float
    if "BLOB" in normalized:
        return str
    return str


def _models_for(
    backend: DatabaseBackend,
    resource: Resource,
) -> tuple[type[BaseModel], type[BaseModel], type[BaseModel] | None, type[BaseModel] | None]:
    fields: dict[str, tuple[Any, Any]] = {}
    columns = backend.columns(resource)
    for column in columns:
        value_type = _python_type(column["type"])
        nullable = not column["notnull"] or bool(column["pk"])
        fields[column["name"]] = (
            value_type | None if nullable else value_type,
            None if nullable else ...,
        )
    item_model = create_model(
        f"{resource.title.replace(' ', '')}Resource",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )
    list_model = create_model(
        f"{resource.title.replace(' ', '')}Collection",
        data=(list[item_model], ...),
        meta=(PaginationMeta, ...),
    )
    create_fields: dict[str, tuple[Any, Any]] = {}
    by_name = {column["name"]: column for column in columns}
    for field in resource.write_fields:
        column = by_name[field]
        value_type = _python_type(column["type"])
        required = (
            field in resource.required_write_fields
            or (bool(column["notnull"]) and column["dflt_value"] is None)
        )
        create_fields[field] = (value_type if required else value_type | None, ... if required else None)
    create_model_type = (
        create_model(
            f"{resource.title.replace(' ', '')}Create",
            __config__=ConfigDict(extra="forbid"),
            **create_fields,
        )
        if create_fields
        else None
    )
    update_fields: dict[str, tuple[Any, Any]] = {}
    for field in (resource.update_fields or resource.write_fields):
        column = by_name[field]
        update_fields[field] = (_python_type(column["type"]) | None, None)
    update_model_type = (
        create_model(
            f"{resource.title.replace(' ', '')}Update",
            __config__=ConfigDict(extra="forbid"),
            **update_fields,
        )
        if update_fields
        else None
    )
    return item_model, list_model, create_model_type, update_model_type


bearer = HTTPBearer(
    auto_error=False,
    scheme_name="FastSME API token",
    description=(
        "Operational reads and all writes require `Authorization: Bearer <token>`. "
        "Synthetic clinical and aggregate reads are public."
    ),
)


def require_write_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),  # noqa: B008
) -> None:
    """Require an explicitly configured bearer token for mutations."""

    configured = os.getenv("FASTSME_API_TOKEN", "")
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "writes_disabled",
                "message": "API writes are disabled until FASTSME_API_TOKEN is configured.",
                "details": {},
            },
        )
    supplied = credentials.credentials if credentials else ""
    if not secrets.compare_digest(configured, supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "A valid bearer token is required for this operation.",
                "details": {},
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_database_api(
    *,
    product: str,
    version: str,
    description: str,
    base_url: str,
    backend: DatabaseBackend,
    resources: tuple[Resource, ...],
    on_mutation: Callable[[str, str, str, dict[str, Any] | None, dict[str, Any] | None], None] | None = None,
) -> FastAPI:
    """Create the product API and register its typed resource routes."""

    api = FastAPI(
        title=f"{product} API",
        version=version,
        description=(
            f"{description}\n\n"
            "**Access model:** synthetic clinical and aggregate reads are public. "
            "Operational reads and every mutation require a bearer token. Those "
            "operations remain disabled until the deployment configures "
            "`FASTSME_API_TOKEN`."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        servers=[{"url": f"{base_url.rstrip('/')}/api", "description": "Production"}],
        contact={"name": "FastSME", "url": "https://fastsme.com"},
        license_info={"name": "MIT"},
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "Idempotency-Key"],
    )

    @api.exception_handler(StarletteHTTPException)
    async def api_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "http_error",
            "message": str(exc.detail),
            "details": {},
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": detail},
            headers=exc.headers,
        )

    @api.exception_handler(RequestValidationError)
    async def api_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request did not match the API schema.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    @api.get("/", tags=["System"])
    def api_index() -> dict[str, Any]:
        return {
            "name": f"{product} API",
            "version": version,
            "documentation": f"{base_url.rstrip('/')}/developers",
            "swagger": f"{base_url.rstrip('/')}/api/docs",
            "openapi": f"{base_url.rstrip('/')}/api/openapi.json",
        }

    @api.get("/v1/health", response_model=HealthResponse, tags=["System"])
    def api_health() -> HealthResponse:
        ready = backend.ready()
        return HealthResponse(
            status="ok" if ready else "degraded",
            product=product,
            version=version,
            writes_enabled=bool(os.getenv("FASTSME_API_TOKEN")),
            database_backend="postgresql" if backend.is_postgres else "sqlite",
            database_ready=ready,
        )

    def register(resource: Resource) -> None:
        item_model, list_model, create_model_type, update_model_type = _models_for(backend, resource)

        @api.get(
            f"/v1/{resource.slug}",
            response_model=list_model,
            tags=[resource.title],
            summary=f"List {resource.title.lower()}",
            description=resource.description,
            operation_id=f"list_{resource.slug.replace('-', '_')}",
        )
        def list_items(
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            q: str | None = Query(default=None, description="Case-insensitive text search"),
        ) -> dict[str, Any]:
            rows, total = backend.list(
                resource, limit=limit, offset=offset, query=q
            )
            return {
                "data": rows,
                "meta": {"total": total, "limit": limit, "offset": offset},
            }

        @api.get(
            f"/v1/{resource.slug}/{{item_id}}",
            response_model=item_model,
            responses={404: {"model": ErrorEnvelope}},
            tags=[resource.title],
            summary=f"Get one {resource.title.lower()} record",
            operation_id=f"get_{resource.slug.replace('-', '_')}",
        )
        def get_item(item_id: str) -> dict[str, Any]:
            row = backend.get(resource, item_id)
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "not_found",
                        "message": f"{resource.title} record not found.",
                        "details": {"id": item_id},
                    },
                )
            return row

        if create_model_type is not None:

            def create_item(payload):
                try:
                    created = backend.create(
                        resource,
                        payload.model_dump(exclude_none=True),
                    )
                    item_id = str(created.get(backend.primary_key(resource), ""))
                    if on_mutation:
                        on_mutation("create", resource.slug, item_id, None, created)
                    return created
                except backend_errors() + (ValueError,) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "invalid_write",
                            "message": "The record could not be created.",
                            "details": {"reason": str(exc)},
                        },
                    ) from exc

            create_item.__annotations__ = {
                "payload": create_model_type,
                "return": dict[str, Any],
            }
            api.post(
                f"/v1/{resource.slug}",
                response_model=item_model,
                status_code=201,
                responses={
                    401: {"model": ErrorEnvelope},
                    422: {"model": ErrorEnvelope},
                    503: {"model": ErrorEnvelope},
                },
                dependencies=[Depends(require_write_token)],
                tags=[resource.title],
                summary=f"Create a {resource.title.lower()} record",
                description=(
                    "Implemented for token-authenticated integrations. Production "
                    "writes remain disabled until FASTSME_API_TOKEN is configured."
                ),
                operation_id=f"create_{resource.slug.replace('-', '_')}",
            )(create_item)

        if update_model_type is not None:

            def update_item(item_id: str, payload):
                try:
                    changed = backend.update(
                        resource,
                        item_id,
                        payload.model_dump(exclude_unset=True),
                    )
                except backend_errors() + (ValueError,) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "invalid_write",
                            "message": "The record could not be updated.",
                            "details": {"reason": str(exc)},
                        },
                    ) from exc
                if changed is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "not_found",
                            "message": f"{resource.title} record not found.",
                            "details": {"id": item_id},
                        },
                    )
                before, after = changed
                if on_mutation:
                    on_mutation("update", resource.slug, item_id, before, after)
                return after

            update_item.__annotations__ = {
                "item_id": str,
                "payload": update_model_type,
                "return": dict[str, Any],
            }
            api.patch(
                f"/v1/{resource.slug}/{{item_id}}",
                response_model=item_model,
                responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
                dependencies=[Depends(require_write_token)],
                tags=[resource.title],
                summary=f"Update a {resource.title.lower()} record",
                operation_id=f"update_{resource.slug.replace('-', '_')}",
            )(update_item)

        if resource.soft_delete_field:

            def delete_item(item_id: str) -> Response:
                try:
                    changed = backend.delete(resource, item_id)
                except backend_errors() + (ValueError,) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "invalid_delete",
                            "message": "The record could not be archived.",
                            "details": {"reason": str(exc)},
                        },
                    ) from exc
                if changed is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "not_found",
                            "message": f"{resource.title} record not found.",
                            "details": {"id": item_id},
                        },
                    )
                before, after = changed
                if on_mutation:
                    on_mutation("archive", resource.slug, item_id, before, after)
                return Response(status_code=204)

            api.delete(
                f"/v1/{resource.slug}/{{item_id}}",
                status_code=204,
                responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
                dependencies=[Depends(require_write_token)],
                tags=[resource.title],
                summary=f"Archive a {resource.title.lower()} record",
                operation_id=f"archive_{resource.slug.replace('-', '_')}",
            )(delete_item)

    for configured_resource in resources:
        register(configured_resource)

    return api


def backend_errors() -> tuple[type[Exception], ...]:
    errors: list[type[Exception]] = [sqlite3.IntegrityError, sqlite3.OperationalError]
    try:
        import psycopg2
        errors.extend([psycopg2.IntegrityError, psycopg2.OperationalError])
    except ImportError:
        pass
    return tuple(errors)


# Compatibility aliases for sister repositories and existing integrations.
SQLiteBackend = DatabaseBackend
create_sqlite_api = create_database_api


def write_swagger(api: FastAPI, destination: str | Path) -> None:
    """Write a deterministic, committed OpenAPI snapshot."""

    path = Path(destination)
    path.write_text(json.dumps(api.openapi(), indent=2, sort_keys=True) + "\n")
