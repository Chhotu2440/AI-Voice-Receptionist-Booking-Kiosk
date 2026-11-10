"""Data access for packages, pricing rules and occasions."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogue import Occasion, Package, PackagePricingRule


async def list_packages(
    session: AsyncSession, *, active_only: bool, offset: int = 0, limit: int | None = None
) -> tuple[Sequence[Package], int]:
    stmt = select(Package).where(Package.deleted_at.is_(None))
    if active_only:
        stmt = stmt.where(Package.is_active.is_(True))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Package.sort_order, Package.name_en).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all(), total


async def get_package(session: AsyncSession, package_id: uuid.UUID) -> Package | None:
    stmt = select(Package).where(Package.id == package_id, Package.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_package_by_code(session: AsyncSession, code: str) -> Package | None:
    return (await session.execute(select(Package).where(Package.code == code))).scalar_one_or_none()


async def rules_for_package(session: AsyncSession, package_id: uuid.UUID) -> Sequence[PackagePricingRule]:
    """Active rules that could apply to this package (package-specific or global)."""
    stmt = select(PackagePricingRule).where(
        PackagePricingRule.is_active.is_(True),
        or_(PackagePricingRule.package_id == package_id, PackagePricingRule.package_id.is_(None)),
    )
    return (await session.execute(stmt)).scalars().all()


async def list_rules(
    session: AsyncSession, *, package_id: uuid.UUID | None, include_inactive: bool, offset: int, limit: int
) -> tuple[Sequence[PackagePricingRule], int]:
    stmt = select(PackagePricingRule)
    if package_id is not None:
        stmt = stmt.where(PackagePricingRule.package_id == package_id)
    if not include_inactive:
        stmt = stmt.where(PackagePricingRule.is_active.is_(True))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = (
        stmt.order_by(PackagePricingRule.rule_type, PackagePricingRule.created_at).offset(offset).limit(limit)
    )
    return (await session.execute(stmt)).scalars().all(), total


async def get_rule(session: AsyncSession, rule_id: uuid.UUID) -> PackagePricingRule | None:
    return await session.get(PackagePricingRule, rule_id)


async def list_occasions(session: AsyncSession, *, active_only: bool) -> Sequence[Occasion]:
    stmt = select(Occasion)
    if active_only:
        stmt = stmt.where(Occasion.is_active.is_(True))
    return (await session.execute(stmt.order_by(Occasion.sort_order))).scalars().all()


async def get_occasion(session: AsyncSession, code: str) -> Occasion | None:
    return (await session.execute(select(Occasion).where(Occasion.code == code))).scalar_one_or_none()
