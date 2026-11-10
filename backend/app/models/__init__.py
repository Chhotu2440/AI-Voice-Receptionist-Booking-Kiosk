"""Import all models so Base.metadata is complete (used by Alembic and tests)."""

from app.models.audit import AuditLog, SystemSetting
from app.models.catalogue import Occasion, Package, PackageFeature, PackagePricingRule
from app.models.identity import Permission, RefreshToken, Role, User, role_permissions, user_roles
from app.models.schedule import BusinessHours, BusinessLocation, Resource, ScheduleException

__all__ = [
    "AuditLog",
    "BusinessHours",
    "BusinessLocation",
    "Occasion",
    "Package",
    "PackageFeature",
    "PackagePricingRule",
    "Permission",
    "RefreshToken",
    "Resource",
    "Role",
    "ScheduleException",
    "SystemSetting",
    "User",
    "role_permissions",
    "user_roles",
]
