"""Admin customers (search, history, consents, correction, export, anonymize) and the audit log viewer."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.api.deps import SessionDep, require_permission, user_actor
from app.core.timeutil import local_to_utc
from app.models.identity import User
from app.schemas.booking import clean_person_name
from app.schemas.common import Page, PageParams
from app.services import audit_service, customer_admin_service

router = APIRouter(prefix="/admin", tags=["admin-customers"])
Paging = Annotated[PageParams, Depends()]


def perm(*codes: str) -> Any:
    return Depends(require_permission(*codes))


class CustomerCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | Literal[""] | None = None
    preferred_language: Literal["en", "hi"] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        # Same rules as a booking (letters, spaces, . ' - only).
        return None if v is None else clean_person_name(v)


class AnonymizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=255)
    confirm: Literal["ANONYMIZE"]


@router.get("/customers")
async def list_customers(
    session: SessionDep, paging: Paging, q: str | None = None, _: User = perm("customer.read")
) -> dict[str, Any]:
    items, total = await customer_admin_service.search(session, q, paging.offset, paging.page_size)
    return Page[dict[str, Any]](
        items=items, page=paging.page, page_size=paging.page_size, total=total
    ).model_dump()


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID, session: SessionDep, _: User = perm("customer.read")
) -> dict[str, Any]:
    return await customer_admin_service.detail(session, customer_id)


@router.patch("/customers/{customer_id}")
async def correct_customer(
    customer_id: uuid.UUID,
    body: CustomerCorrection,
    request: Request,
    session: SessionDep,
    user: User = perm("customer.write"),
) -> dict[str, Any]:
    return await customer_admin_service.correct(
        session,
        customer_id,
        user_actor(user, request),
        name=body.name,
        email=body.email,
        preferred_language=body.preferred_language,
    )


@router.get("/customers/{customer_id}/export")
async def export_customer(
    customer_id: uuid.UUID, request: Request, session: SessionDep, user: User = perm("customer.write")
) -> JSONResponse:
    data = await customer_admin_service.export(session, customer_id, user_actor(user, request))
    return JSONResponse(
        data,
        headers={
            "Content-Disposition": f'attachment; filename="customer-{customer_id}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/customers/{customer_id}/anonymize")
async def anonymize_customer(
    customer_id: uuid.UUID,
    body: AnonymizeRequest,
    request: Request,
    session: SessionDep,
    user: User = perm("customer.write"),
) -> dict[str, Any]:
    return await customer_admin_service.anonymize(
        session, customer_id, body.reason, user_actor(user, request)
    )


@router.get("/audit")
async def audit_log(
    session: SessionDep,
    paging: Paging,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    _: User = perm("audit.read"),
) -> dict[str, Any]:
    items, total = await audit_service.search(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        date_from=local_to_utc(date_from, time(0)) if date_from else None,
        date_to=local_to_utc(date_to + timedelta(days=1), time(0)) if date_to else None,
        offset=paging.offset,
        limit=paging.page_size,
    )
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}
