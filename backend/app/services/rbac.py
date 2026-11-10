"""Canonical permission catalogue and default role grants. Seeded idempotently by `app.cli seed`."""

from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    "dashboard.read": "View dashboard and reports",
    "catalogue.write": "Create and edit packages and occasions",
    "pricing.write": "Edit pricing rules and pricing settings",
    "schedule.read": "View hours, exceptions and resources",
    "schedule.write": "Edit hours, holidays, blocks and resources",
    "booking.read": "View bookings",
    "booking.write": "Create, cancel and reschedule bookings",
    "customer.read": "View customers",
    "customer.write": "Edit, export and anonymize customers",
    "enquiry.manage": "Manage event enquiries",
    "kiosk.manage": "Pair and configure kiosks",
    "ai.config": "Configure AI provider, voice and spend caps",
    "settings.write": "Edit business settings",
    "user.manage": "Manage staff accounts and roles",
    "audit.read": "View the audit log",
}

ROLE_NAMES: dict[str, str] = {
    "OWNER": "Owner",
    "MANAGER": "Manager",
    "STAFF": "Front desk",
    "VIEWER": "Viewer",
}

ROLE_GRANTS: dict[str, set[str]] = {
    "OWNER": set(PERMISSIONS),
    "MANAGER": set(PERMISSIONS) - {"user.manage", "ai.config", "settings.write"},
    "STAFF": {
        "dashboard.read",
        "schedule.read",
        "booking.read",
        "booking.write",
        "customer.read",
        "enquiry.manage",
    },
    "VIEWER": {"dashboard.read", "schedule.read", "booking.read"},
}
