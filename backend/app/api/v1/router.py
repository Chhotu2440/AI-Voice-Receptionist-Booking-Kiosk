from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, public

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(admin.router)
