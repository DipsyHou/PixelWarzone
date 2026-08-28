import time
import random
from typing import Optional

from fastapi import WebSocket
import server_config as cfg

MAP_WIDTH = cfg.MAP_WIDTH
MAP_HEIGHT = cfg.MAP_HEIGHT
DEFAULT_WEAPON_SLOTS = ["single", "shotgun", "crossbomb", "wall"]


class Room:
    def __init__(
        self,
        room_id: str,
        name: str,
        creator: str,
        max_players: int = 8,
        password: Optional[str] = None,
    ):
        self.room_id = room_id
        self.name = name
        self.creator = creator
        self.max_players = max_players
        self.password = password
        self.created_at = time.time()

        self.players: dict = {}
        self.connections: dict = {}

        self.bullets: list = []
        self.walls: list = []
        self.graffiti: dict = {}
        self.smokes: list = []
        self.turrets: list = []
        self.cross_bombs: list = []

        self.game_running: bool = False

    def add_player(
        self,
        username: str,
        websocket: Optional[WebSocket],
        loadout: Optional[dict] = None,
    ) -> bool:
        if len(self.players) >= self.max_players:
            return False

        loadout = loadout or {}
        weapon_slots = loadout.get("weapon_slots", DEFAULT_WEAPON_SLOTS)[:4]
        perks = loadout.get("perks", [])

        self.players[username] = {
            "x": random.randint(100, MAP_WIDTH - 100),
            "y": random.randint(100, MAP_HEIGHT - 100),
            "dx": 0,
            "dy": 0,
            "target_dx": 0,
            "target_dy": 0,
            "hp": cfg.PLAYER_MAX_HP,
            "last_hit": time.time(),
            "kills": 0,
            "deaths": 0,
            "weapon_slots": weapon_slots,
            "perks": perks,
            "active_weapon": weapon_slots[0] if weapon_slots else "single",
            "weapon_ready_at": 0.0,
            "switch_ready_at": 0.0,
            "iaido_charges": 1 if (weapon_slots and weapon_slots[0] == "iaido") else 0,
            "iaido_charge_accum": 0.0,
        }
        self.connections[username] = websocket
        return True

    def remove_player(self, username: str):
        self.players.pop(username, None)
        self.connections.pop(username, None)
        if not self.players and self.game_running:
            self.game_running = False

    def get_state(self) -> dict:
        now = time.time()
        state_players = {}
        for username, player in self.players.items():
            p = player.copy()
            p["status"] = "dead" if p["hp"] <= 0 else "alive"
            p["hp"] = max(0, int(p.get("hp", 0)))
            p["weapon_cd_ms"] = max(0, int((p.get("weapon_ready_at", 0) - now) * 1000))
            p["switch_cd_ms"] = max(0, int((p.get("switch_ready_at", 0) - now) * 1000))
            p["iaido_charges"] = int(p.get("iaido_charges", 0))
            charges = p["iaido_charges"]
            interval = (
                cfg.IAIDO_CHARGE_INTERVAL_EMPTY_SEC
                if charges <= 0
                else cfg.IAIDO_CHARGE_INTERVAL_SEC
            )
            accum = float(p.get("iaido_charge_accum", 0.0))
            p["iaido_charge_progress"] = (
                0.0 if charges >= cfg.IAIDO_CHARGE_MAX else min(1.0, accum / max(interval, 1e-6))
            )
            # Internal timers not needed by clients
            p.pop("weapon_ready_at", None)
            p.pop("switch_ready_at", None)
            p.pop("iaido_charge_accum", None)
            p.pop("last_iaido", None)
            p.pop("iaido_dash", None)
            state_players[username] = p

        return {
            "players": state_players,
            "bullets": self.bullets,
            "walls": self.walls,
            "graffiti": self.graffiti,
            "smokes": self.smokes,
            "turrets": self.turrets,
            "cross_bombs": self.cross_bombs,
            "room_info": {
                "name": self.name,
                "player_count": len(self.players),
                "players_count": len(self.players),
                "max_players": self.max_players,
            },
        }

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "creator": self.creator,
            "max_players": self.max_players,
            "password": self.password,
            "players": self.players,
            "bullets": self.bullets,
            "game_running": self.game_running,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Room":
        room = Room(
            room_id=d["room_id"],
            name=d["name"],
            creator=d["creator"],
            max_players=d.get("max_players", 8),
            password=d.get("password"),
        )
        room.players = d.get("players", {})
        room.bullets = d.get("bullets", [])
        room.game_running = d.get("game_running", False)
        room.created_at = d.get("created_at", time.time())
        return room
