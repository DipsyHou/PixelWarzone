"""
Dispatches incoming WebSocket messages to the appropriate handler function.

Combat rules live entirely on the server. Clients send intents (aim / direction);
damage, range, speed, cooldowns and charges are applied from server_config.
"""

import time
import math
import uuid
import random
import logging
from collections import defaultdict

import server_config as cfg
from utils import _dist_point_to_segment
from room import Room

logger = logging.getLogger(__name__)

MAP_WIDTH = cfg.MAP_WIDTH
MAP_HEIGHT = cfg.MAP_HEIGHT

AVAILABLE_WEAPONS = {
    "single", "shotgun", "missile", "wall",
    "smoke", "turret", "iaido", "crossbomb",
}

_HANDLERS: dict = {}


def _register(msg_type: str):
    def decorator(fn):
        _HANDLERS[msg_type] = fn
        return fn
    return decorator


def handle_message(room: Room, username: str, msg: dict):
    handler = _HANDLERS.get(msg.get("type"))
    if handler:
        handler(room, username, msg)


def _alive(p: dict) -> bool:
    return p.get("hp", 0) > 0


def _weapon_ready(p: dict, now: float) -> bool:
    return now >= float(p.get("weapon_ready_at", 0))


def _set_weapon_cd(p: dict, now: float, cd_sec: float):
    p["weapon_ready_at"] = now + cd_sec


def _aim_dir(msg: dict, px: float, py: float):
    """Resolve a unit aim direction from dirx/diry or aim_x/aim_y."""
    if "dirx" in msg or "diry" in msg:
        dx = float(msg.get("dirx", 0))
        dy = float(msg.get("diry", 0))
    else:
        dx = float(msg.get("aim_x", px)) - px
        dy = float(msg.get("aim_y", py)) - py
    norm = math.hypot(dx, dy)
    if norm <= 1e-6:
        return None
    return dx / norm, dy / norm


def _clamp_place(px, py, tx, ty, max_dist):
    dx, dy = tx - px, ty - py
    dist = math.hypot(dx, dy)
    if max_dist > 0 and dist > max_dist and dist > 0:
        r = max_dist / dist
        tx, ty = px + dx * r, py + dy * r
    return tx, ty


def _spawn_bullet(room, p, username, ux, uy, speed, max_dist, damage, btype="normal"):
    room.bullets.append({
        "x": p["x"], "y": p["y"],
        "dx": ux * speed,
        "dy": uy * speed,
        "owner": username,
        "hit_set": [],
        "start_x": p["x"], "start_y": p["y"],
        "max_dist": max_dist,
        "damage": damage,
        "created_at": time.time(),
        "type": btype,
        **({"target": None, "exploded": False} if btype == "missile" else {}),
    })


# ──────────────────────────────────────────────
#  Movement
# ──────────────────────────────────────────────

@_register("move")
def _handle_move(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    p = room.players[username]
    dx = float(msg.get("dx", 0))
    dy = float(msg.get("dy", 0))
    speed = math.hypot(dx, dy)
    max_speed = cfg.PLAYER_SPEED
    if speed > max_speed and speed > 0:
        dx = dx / speed * max_speed
        dy = dy / speed * max_speed
    p["target_dx"] = dx
    p["target_dy"] = dy


# ──────────────────────────────────────────────
#  Cosmetics
# ──────────────────────────────────────────────

@_register("graffiti")
def _handle_graffiti(room: Room, username: str, msg: dict):
    if username in room.players:
        room.graffiti[username] = {
            "x": int(msg.get("x", 0)),
            "y": int(msg.get("y", 0)),
        }


# ──────────────────────────────────────────────
#  Weapon switch
# ──────────────────────────────────────────────

@_register("switch_weapon")
def _handle_switch_weapon(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    p = room.players[username]
    weapon = msg.get("weapon")
    if weapon not in AVAILABLE_WEAPONS:
        return
    slots = p.get("weapon_slots") or []
    if weapon not in slots:
        return
    if p.get("active_weapon") == weapon:
        return
    now = time.time()
    if now < float(p.get("switch_ready_at", 0)):
        return

    p["active_weapon"] = weapon
    p["switch_ready_at"] = now + cfg.SWITCH_WEAPON_CD_SEC
    if weapon == "iaido":
        p["iaido_charges"] = max(1, int(p.get("iaido_charges", 0)))
        p["iaido_charge_accum"] = 0.0
        p["weapon_ready_at"] = 0.0


# ──────────────────────────────────────────────
#  Fire (uses active_weapon)
# ──────────────────────────────────────────────

@_register("fire")
def _handle_fire(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    p = room.players[username]
    if not _alive(p):
        return
    now = time.time()
    weapon = p.get("active_weapon", "single")

    if weapon == "iaido":
        _do_iaido(room, username, p, msg, now)
        return

    if not _weapon_ready(p, now):
        return

    handlers = {
        "single": _do_single,
        "shotgun": _do_shotgun,
        "missile": _do_missile,
        "wall": _do_wall,
        "smoke": _do_smoke,
        "turret": _do_turret,
        "crossbomb": _do_cross_bomb,
    }
    fn = handlers.get(weapon)
    if fn:
        fn(room, username, p, msg, now)


# Legacy aliases (still accepted, routed through same logic)
@_register("shoot")
def _handle_shoot_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    # Prefer explicit weapon if client still sends old multi-bullet shotgun
    weapon = msg.get("weapon") or room.players[username].get("active_weapon", "single")
    if weapon not in ("single", "shotgun"):
        weapon = "single"
    room.players[username]["active_weapon"] = weapon
    msg = {**msg, "type": "fire"}
    if "dirx" not in msg and "dx" in msg:
        msg["dirx"] = msg.get("dx")
        msg["diry"] = msg.get("dy")
    _handle_fire(room, username, msg)


@_register("shoot_missile")
def _handle_missile_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "missile"
    if "dirx" not in msg and "dx" in msg:
        msg = {**msg, "dirx": msg.get("dx"), "diry": msg.get("dy")}
    _handle_fire(room, username, msg)


@_register("smoke_grenade")
def _handle_smoke_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "smoke"
    _handle_fire(room, username, msg)


@_register("build_wall")
def _handle_wall_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "wall"
    _handle_fire(room, username, msg)


@_register("summon_turret")
def _handle_turret_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "turret"
    _handle_fire(room, username, msg)


@_register("place_cross_bomb")
def _handle_cross_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "crossbomb"
    _handle_fire(room, username, msg)


@_register("iaido")
def _handle_iaido_legacy(room: Room, username: str, msg: dict):
    if username not in room.players:
        return
    room.players[username]["active_weapon"] = "iaido"
    _handle_fire(room, username, msg)


# ──────────────────────────────────────────────
#  Weapon implementations
# ──────────────────────────────────────────────

def _do_single(room, username, p, msg, now):
    aim = _aim_dir(msg, p["x"], p["y"])
    if not aim:
        return
    ux, uy = aim
    _spawn_bullet(room, p, username, ux, uy, cfg.BULLET_SPEED, cfg.BULLET_RANGE, cfg.BULLET_DAMAGE)
    _set_weapon_cd(p, now, cfg.BULLET_CD_SEC)
    p["last_hit"] = now


def _do_shotgun(room, username, p, msg, now):
    aim = _aim_dir(msg, p["x"], p["y"])
    if not aim:
        return
    ux, uy = aim
    base = math.atan2(uy, ux)
    count = cfg.SHOTGUN_PELLET_COUNT
    spread = cfg.SHOTGUN_SPREAD
    for i in range(count):
        a = base - spread / 2 + (spread / max(count - 1, 1)) * i
        _spawn_bullet(
            room, p, username,
            math.cos(a), math.sin(a),
            cfg.SHOTGUN_SPEED, cfg.SHOTGUN_RANGE, cfg.SHOTGUN_DAMAGE,
        )
    _set_weapon_cd(p, now, cfg.SHOTGUN_CD_SEC)
    p["last_hit"] = now


def _do_missile(room, username, p, msg, now):
    aim = _aim_dir(msg, p["x"], p["y"])
    if not aim:
        return
    ux, uy = aim
    _spawn_bullet(
        room, p, username, ux, uy,
        cfg.MISSILE_SPEED, cfg.MISSILE_RANGE, cfg.MISSILE_DAMAGE, "missile",
    )
    _set_weapon_cd(p, now, cfg.MISSILE_CD_SEC)
    p["last_hit"] = now


def _do_wall(room, username, p, msg, now):
    px, py = p["x"], p["y"]
    tx = float(msg.get("aim_x", msg.get("x", px)))
    ty = float(msg.get("aim_y", msg.get("y", py)))
    tx, ty = _clamp_place(px, py, tx, ty, cfg.WALL_PLACE_RANGE)
    x, y = int(tx), int(ty)

    angle = abs(math.atan2(y - py, x - px))
    bs = cfg.WALL_BLOCK_SIZE
    blocks = []
    if angle < math.pi / 4 or angle > 3 * math.pi / 4:
        for i in range(-4, 4):
            blocks.append({"x": x, "y": y + i * bs})
    else:
        for i in range(-4, 4):
            blocks.append({"x": x + i * bs, "y": y})

    # Reject if a living player overlaps any block
    p_radius = cfg.PLAYER_RADIUS + 24
    for b in blocks:
        for uname, other in room.players.items():
            if other.get("hp", 0) <= 0:
                continue
            if math.hypot(b["x"] - other["x"], b["y"] - other["y"]) < p_radius:
                return

    room.walls.append({
        "x": x, "y": y,
        "owner": username,
        "blocks": blocks,
        "created_at": now,
    })
    _set_weapon_cd(p, now, cfg.WALL_CD_SEC)
    p["last_hit"] = now


def _do_smoke(room, username, p, msg, now):
    px, py = p["x"], p["y"]
    tx = float(msg.get("aim_x", msg.get("x", px)))
    ty = float(msg.get("aim_y", msg.get("y", py)))
    tx, ty = _clamp_place(px, py, tx, ty, cfg.SMOKE_PLACE_RANGE)
    room.smokes.append({
        "x": int(tx),
        "y": int(ty),
        "radius": cfg.SMOKE_DEFAULT_RADIUS,
        "owner": username,
        "created_at": now,
        "duration": float(cfg.SMOKE_DEFAULT_DURATION),
    })
    _set_weapon_cd(p, now, cfg.SMOKE_CD_SEC)
    p["last_hit"] = now


def _do_turret(room, username, p, msg, now):
    px, py = p["x"], p["y"]
    tx = float(msg.get("aim_x", msg.get("x", px)))
    ty = float(msg.get("aim_y", msg.get("y", py)))
    tx, ty = _clamp_place(px, py, tx, ty, cfg.TURRET_PLACE_LIMIT)
    room.turrets.append({
        "x": int(tx),
        "y": int(ty),
        "hp": cfg.TURRET_INITIAL_HP,
        "owner": username,
        "created_at": now,
        "last_fire": 0.0,
    })
    _set_weapon_cd(p, now, cfg.TURRET_PLACE_CD_SEC)
    p["last_hit"] = now


def _do_cross_bomb(room, username, p, msg, now):
    px, py = p["x"], p["y"]
    tx = float(msg.get("aim_x", msg.get("x", px)))
    ty = float(msg.get("aim_y", msg.get("y", py)))
    tx, ty = _clamp_place(px, py, tx, ty, cfg.CROSS_BOMB_PLACE_DISTANCE)
    if math.hypot(tx - px, ty - py) <= 0:
        tx, ty = px + 1, py

    fx = max(20, min(MAP_WIDTH - 20, tx))
    fy = max(20, min(MAP_HEIGHT - 20, ty))
    angle = math.atan2(fy - py, fx - px)

    bomb = {
        "id": str(uuid.uuid4())[:8],
        "x": int(fx), "y": int(fy),
        "owner": username,
        "angle": angle,
        "dirx": math.cos(angle),
        "diry": math.sin(angle),
        "planted_at": now,
        "explode_at": now + cfg.CROSS_BOMB_FUSE_SEC,
        "state": "armed",
    }

    active = [b for b in room.cross_bombs
              if b.get("owner") == username and b.get("state") != "detonating"]
    if cfg.CROSS_BOMB_MAX_ACTIVE_PER_PLAYER > 0 and len(active) >= cfg.CROSS_BOMB_MAX_ACTIVE_PER_PLAYER:
        oldest = min(active, key=lambda b: b.get("planted_at", 0))
        try:
            room.cross_bombs.remove(oldest)
        except ValueError:
            pass

    room.cross_bombs.append(bomb)
    _set_weapon_cd(p, now, cfg.CROSS_BOMB_CD_SEC)
    p["last_hit"] = now


def _do_iaido(room, username, p, msg, now):
    charges = int(p.get("iaido_charges", 0))
    if charges < 1:
        return

    aim = _aim_dir(msg, p["x"], p["y"])
    if not aim:
        return
    dirx, diry = aim

    # Hold time from client is advisory for distance only (clamped)
    try:
        hold_ms = float(msg.get("hold_ms", 0))
    except Exception:
        hold_ms = 0.0
    hold_ms = max(0.0, min(hold_ms, cfg.IAIDO_HOLD_MAX_SEC * 1000))
    t = hold_ms / max(cfg.IAIDO_HOLD_MAX_SEC * 1000, 1.0)
    dist = cfg.IAIDO_MIN_DISTANCE + (cfg.IAIDO_DISTANCE - cfg.IAIDO_MIN_DISTANCE) * t

    damage = cfg.IAIDO_DAMAGE
    sx, sy = p["x"], p["y"]
    ex = max(20, min(MAP_WIDTH - 20, int(sx + dirx * dist)))
    ey = max(20, min(MAP_HEIGHT - 20, int(sy + diry * dist)))
    tx, ty = ex, ey

    thresh = (cfg.WALL_BLOCK_SIZE / 2.0) + cfg.IAIDO_WIDTH
    to_remove: list[tuple[int, int]] = []
    for w_idx, wall in enumerate(room.walls):
        for b_idx, block in enumerate(wall["blocks"]):
            if _dist_point_to_segment(block["x"], block["y"], sx, sy, tx, ty) <= thresh:
                to_remove.append((w_idx, b_idx))
    if to_remove:
        grouped = defaultdict(list)
        for wi, bi in to_remove:
            grouped[wi].append(bi)
        for wi, bis in grouped.items():
            blocks = room.walls[wi]["blocks"]
            for bi in sorted(bis, reverse=True):
                if 0 <= bi < len(blocks):
                    blocks.pop(bi)
        room.walls = [w for w in room.walls if w["blocks"]]

    dash_dist = math.hypot(tx - sx, ty - sy) or 1
    p["iaido_dash"] = {
        "sx": sx, "sy": sy,
        "ex": tx, "ey": ty,
        "start": now,
        "duration": dash_dist / max(1.0, cfg.IAIDO_SPEED),
    }
    p["last_iaido"] = now
    p["last_hit"] = now
    p["iaido_charges"] = charges - 1

    for uname, other in room.players.items():
        if uname == username or other["hp"] <= 0:
            continue
        if _dist_point_to_segment(other["x"], other["y"], sx, sy, tx, ty) <= cfg.IAIDO_WIDTH:
            other["hp"] -= damage
            other["last_hit"] = now
            if other["hp"] <= 0:
                other["hp"] = 0
                p["kills"] += 1
                other["deaths"] += 1

    turret_remove: set = set()
    for i, turr in enumerate(room.turrets):
        if turr.get("owner") == username or turr.get("hp", 0) <= 0:
            continue
        if _dist_point_to_segment(turr["x"], turr["y"], sx, sy, tx, ty) <= cfg.IAIDO_WIDTH:
            turr["hp"] = max(0, turr["hp"] - damage)
            if turr["hp"] <= 0:
                turret_remove.add(i)
    if turret_remove:
        room.turrets = [t for j, t in enumerate(room.turrets) if j not in turret_remove]


# ──────────────────────────────────────────────
#  Respawn
# ──────────────────────────────────────────────

@_register("respawn")
def _handle_respawn(room: Room, username: str, msg: dict):
    if username in room.players and room.players[username]["hp"] <= 0:
        room.players[username].update({
            "x": random.randint(100, MAP_WIDTH - 100),
            "y": random.randint(100, MAP_HEIGHT - 100),
            "hp": cfg.PLAYER_MAX_HP,
            "last_hit": time.time(),
        })
