"""
Application entry point.

Creates the FastAPI app, registers middleware / routes / WebSocket,
manages the game-loop lifecycle, and serves the static frontend.
"""

import os
import time
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from data_store import store
from game_logic import game_loop
from ws_handler import websocket_endpoint
from routes import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

game_loop_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global game_loop_task
    logger.info("Starting game server...")
    game_loop_task = asyncio.create_task(game_loop())
    try:
        yield
    finally:
        logger.info("Saving all data before shutdown...")
        store.save_all()
        if game_loop_task and not game_loop_task.done():
            game_loop_task.cancel()
            try:
                await game_loop_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Battle Royale Game API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(api_router)

# WebSocket route
app.websocket("/ws/{room_id}")(websocket_endpoint)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "users_count": len(store.users_db),
        "active_sessions": len(store.sessions),
        "active_rooms": len(store.rooms),
        "total_players": sum(len(r.players) for r in store.rooms.values()),
    }


# Static frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
