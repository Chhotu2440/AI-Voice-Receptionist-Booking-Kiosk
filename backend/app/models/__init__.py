"""Import all models so Base.metadata is complete (used by Alembic and tests)."""

from app.models.audit import AuditLog, SystemSetting
from app.models.booking import (
    AvailabilitySlot,
    Booking,
    BookingItem,
    BookingPricingSnapshot,
    BookingSlot,
    BookingStatusHistory,
    Customer,
    CustomerConsent,
    CustomEventEnquiry,
    IdempotencyKey,
    SlotHold,
    SlotHoldCell,
)
from app.models.catalogue import Occasion, Package, PackageFeature, PackagePricingRule
from app.models.identity import Permission, RefreshToken, Role, User, role_permissions, user_roles
from app.models.kiosk import KioskDevice, KioskSession
from app.models.notification import NotificationLog, WebhookEvent
from app.models.schedule import BusinessHours, BusinessLocation, Resource, ScheduleException

__all__ = [
    "AuditLog",
    "AvailabilitySlot",
    "Booking",
    "BookingItem",
    "BookingPricingSnapshot",
    "BookingSlot",
    "BookingStatusHistory",
    "BusinessHours",
    "BusinessLocation",
    "CustomEventEnquiry",
    "Customer",
    "CustomerConsent",
    "IdempotencyKey",
    "KioskDevice",
    "KioskSession",
    "NotificationLog",
    "Occasion",
    "Package",
    "PackageFeature",
    "PackagePricingRule",
    "Permission",
    "RefreshToken",
    "Resource",
    "Role",
    "ScheduleException",
    "SlotHold",
    "SlotHoldCell",
    "SystemSetting",
    "User",
    "WebhookEvent",
    "role_permissions",
    "user_roles",
]
