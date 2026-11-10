from fastapi import APIRouter

from app.api.v1.endpoints import admin, admin_bookings, auth, booking, kiosk, public

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(booking.router)
api_router.include_router(admin.router)
api_router.include_router(admin_bookings.router)
api_router.include_router(kiosk.router)
