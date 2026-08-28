from fastapi import APIRouter

from routes.auth_routes import router as auth_router
from routes.room_routes import router as room_router
from routes.game_routes import router as game_router
from routes.admin_routes import router as admin_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(room_router)
api_router.include_router(game_router)
api_router.include_router(admin_router)
