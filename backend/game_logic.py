"""
Core game-loop mechanics: movement, physics, damage, regeneration.

Every public function operates on a single Room and is called once per tick.
"""

import time
import math
import json
import asyncio
import logging
from collections import defaultdict

import server_config as cfg
from utils import _dist_point_to_segment, circle_aabb_overlap, distance
from room import Room

logger = logging.getLogger(__name__)

MAP_WIDTH = cfg.MAP_WIDTH
MAP_HEIGHT = cfg.MAP_HEIGHT


# ──────────────────────────────────────────────
#  Cross-bomb helpers
# ──────────────────────────────────────────────

def point_in_cross_area(bomb: dict, x: float, y: float) -> bool:
    bx, by = bomb.get("x", 0.0), bomb.get("y", 0.0)
    dirx, diry = bomb.get("dirx", 1.0), bomb.get("diry", 0.0)
    norm = math.hypot(dirx, diry) or 1.0
    ux, uy = dirx / norm, diry / norm
    vx, vy = x - bx, y - by
    proj = vx * ux + vy * uy
    perp = -vx * uy + vy * ux
    length = cfg.CROSS_BOMB_ARM_LENGTH
    hw = cfg.CROSS_BOMB_ARM_HALF_WIDTH
    if abs(proj) <= length and abs(perp) <= hw:
        return True
    if abs(perp) <= length and abs(proj) <= hw:
        return True
    return False


def apply_cross_bomb_damage(room: Room, bomb: dict, now_ts: float):
    owner = bomb.get("owner")
    dmg = cfg.CROSS_BOMB_DAMAGE

    for uname, player in room.players.items():
        if player.get("hp", 0) <= 0 or (owner and uname == owner):
            continue
        if point_in_cross_area(bomb, player.get("x", 0), player.get("y", 0)):
            player["hp"] = max(0, player["hp"] - dmg)
            player["last_hit"] = now_ts
            if player["hp"] <= 0:
                player["deaths"] = player.get("deaths", 0) + 1
                if owner and owner != uname and owner in room.players:
                    room.players[owner]["kills"] = room.players[owner].get("kills", 0) + 1

    for turret in room.turrets:
        if turret.get("hp", 0) <= 0:
            continue
        if point_in_cross_area(bomb, turret.get("x", 0), turret.get("y", 0)):
            turret["hp"] = max(0, turret["hp"] - dmg)

    _destroy_wall_blocks(room, lambda bx, by: point_in_cross_area(bomb, bx, by))


def _destroy_wall_blocks(room: Room, predicate):
    """Remove wall blocks where *predicate(block_x, block_y)* is True."""
    remove_map: list[tuple[int, int]] = []
    for w_idx, wall in enumerate(room.walls):
        for b_idx, block in enumerate(wall.get("blocks", [])):
            if predicate(block.get("x", 0), block.get("y", 0)):
                remove_map.append((w_idx, b_idx))
    if not remove_map:
        return
    grouped = defaultdict(list)
    for w_idx, b_idx in remove_map:
        grouped[w_idx].append(b_idx)
    for w_idx, b_idxs in grouped.items():
        if 0 <= w_idx < len(room.walls):
            blocks = room.walls[w_idx].get("blocks", [])
            for b_idx in sorted(b_idxs, reverse=True):
                if 0 <= b_idx < len(blocks):
                    blocks.pop(b_idx)
    room.walls = [w for w in room.walls if w.get("blocks")]


# ──────────────────────────────────────────────
#  Per-tick update functions
# ──────────────────────────────────────────────

def update_walls(room: Room, now: float):
    room.walls = [
        w for w in room.walls
        if now - w.get("created_at", now) < cfg.WALL_LIFETIME_SEC
    ]


def update_smokes(room: Room, now: float):
    updated = []
    for s in room.smokes:
        elapsed = now - s.get("created_at", now)
        if elapsed < s.get("duration", 8):
            progress = min(elapsed / cfg.SMOKE_APPEAR_ANIM_SEC, 1.0)
            s["current_radius"] = s.get("radius", cfg.SMOKE_DEFAULT_RADIUS) * progress
            updated.append(s)
    room.smokes = updated


def update_cross_bombs(room: Room, now: float):
    armed, detonating, trigger_queue = [], [], []

    for bomb in room.cross_bombs:
        state = bomb.get("state", "armed")
        if state == "armed":
            if now >= bomb.get("explode_at", now):
                trigger_queue.append(bomb)
            else:
                armed.append(bomb)
        elif state == "detonating":
            if now - bomb.get("detonate_time", now) <= cfg.CROSS_BOMB_EXPLOSION_DURATION:
                detonating.append(bomb)

    processed_ids: set = set()
    while trigger_queue:
        bomb = trigger_queue.pop(0)
        bid = bomb.get("id")
        if bid in processed_ids:
            continue
        processed_ids.add(bid)

        bomb["state"] = "detonating"
        bomb["detonate_time"] = now
        apply_cross_bomb_damage(room, bomb, now)

        owner = bomb.get("owner")
        remaining = []
        for other in armed:
            if (other.get("owner") == owner
                    and point_in_cross_area(bomb, other.get("x", 0), other.get("y", 0))):
                other["state"] = "detonating"
                other["detonate_time"] = now
                trigger_queue.append(other)
            else:
                remaining.append(other)
        armed = remaining
        detonating.append(bomb)

    room.cross_bombs = armed + detonating


# ──────────────────────────────────────────────
#  Player movement
# ──────────────────────────────────────────────

def update_player_movement(room: Room, now: float):
    for player in room.players.values():
        if _apply_iaido_dash(player, now):
            continue
        _apply_inertia(player)
        _apply_wall_collision(room, player)


def _apply_iaido_dash(player: dict, now: float) -> bool:
    dash = player.get("iaido_dash")
    if not dash:
        return False
    t = (now - dash.get("start", now)) / max(1e-6, dash.get("duration", 0.001))
    if t >= 1:
        player["x"] = dash.get("ex", player["x"])
        player["y"] = dash.get("ey", player["y"])
        player.pop("iaido_dash", None)
    else:
        player["x"] = dash["sx"] + (dash["ex"] - dash["sx"]) * t
        player["y"] = dash["sy"] + (dash["ey"] - dash["sy"]) * t
    return True


def _apply_inertia(player: dict):
    inertia = 0.85
    player["dx"] = player.get("dx", 0) * inertia + player.get("target_dx", 0) * (1 - inertia)
    player["dy"] = player.get("dy", 0) * inertia + player.get("target_dy", 0) * (1 - inertia)
    if abs(player["dx"]) < 0.1:
        player["dx"] = 0
    if abs(player["dy"]) < 0.1:
        player["dy"] = 0


def _clamp_player_pos(x: float, y: float) -> tuple[float, float]:
    return (
        max(20, min(MAP_WIDTH - 20, x)),
        max(20, min(MAP_HEIGHT - 20, y)),
    )


def _apply_wall_collision(room: Room, player: dict):
    """Move with wall slide: blocked axis is dropped, remaining motion keeps full speed.

    Example: holding up-right into a vertical wall → slide straight up at full
    speed (not the diagonal component 0.707).
    """
    dx = float(player.get("dx", 0))
    dy = float(player.get("dy", 0))
    speed = math.hypot(dx, dy)
    x, y = player["x"], player["y"]

    trial_x, _ = _clamp_player_pos(x + dx, y)
    _, trial_y = _clamp_player_pos(x, y + dy)

    blocked_x = abs(dx) > 1e-8 and _hits_wall(room, trial_x, y)
    blocked_y = abs(dy) > 1e-8 and _hits_wall(room, x, trial_y)

    if not blocked_x and not blocked_y:
        nx, ny = _clamp_player_pos(x + dx, y + dy)
        if not _hits_wall(room, nx, ny):
            player["x"], player["y"] = nx, ny
            return
        # Combined step hits a corner; fall back to axis split without boost.
        if not _hits_wall(room, trial_x, y):
            player["x"] = trial_x
        if not _hits_wall(room, player["x"], trial_y):
            player["y"] = trial_y
        return

    if blocked_x and not blocked_y:
        # Vertical surface: redirect full speed onto Y.
        if abs(dy) > 1e-8 and speed > 0:
            slide_dy = math.copysign(speed, dy)
            _, ny = _clamp_player_pos(x, y + slide_dy)
            if not _hits_wall(room, x, ny):
                player["y"] = ny
                player["dx"] = 0.0
                player["dy"] = slide_dy
                return
        player["dx"] = 0.0
        return

    if blocked_y and not blocked_x:
        # Horizontal surface: redirect full speed onto X.
        if abs(dx) > 1e-8 and speed > 0:
            slide_dx = math.copysign(speed, dx)
            nx, _ = _clamp_player_pos(x + slide_dx, y)
            if not _hits_wall(room, nx, y):
                player["x"] = nx
                player["dx"] = slide_dx
                player["dy"] = 0.0
                return
        player["dy"] = 0.0
        return

    # Both axes blocked (corner / pocket).
    player["dx"] = 0.0
    player["dy"] = 0.0


def _hits_wall(room: Room, x: float, y: float) -> bool:
    half = cfg.WALL_BLOCK_SIZE / 2
    radius = float(getattr(cfg, "PLAYER_RADIUS", 30))
    for wall in room.walls:
        for block in wall["blocks"]:
            if circle_aabb_overlap(x, y, radius, block["x"], block["y"], half):
                return True
    return False


# ──────────────────────────────────────────────
#  Bullets (movement + wall collision)
# ──────────────────────────────────────────────

def update_bullets(room: Room, now: float):
    new_bullets = []
    wall_blocks_to_remove: list[tuple[int, int]] = []

    for bullet in room.bullets:
        hit_wall = False
        for w_idx, wall in enumerate(room.walls):
            for b_idx, block in enumerate(wall["blocks"]):
                if distance(bullet["x"], bullet["y"], block["x"], block["y"]) < 20:
                    wall_blocks_to_remove.append((w_idx, b_idx))
                    hit_wall = True

        if hit_wall:
            continue

        if bullet.get("type") == "missile" and not bullet.get("exploded", False):
            _track_missile(room, bullet)

        bullet["x"] += bullet["dx"]
        bullet["y"] += bullet["dy"]
        dist = distance(bullet["x"], bullet["y"], bullet["start_x"], bullet["start_y"])
        if (0 < bullet["x"] < MAP_WIDTH
                and 0 < bullet["y"] < MAP_HEIGHT
                and dist < bullet["max_dist"]
                and now - bullet["created_at"] < cfg.BULLET_MAX_LIFETIME_SEC
                and not bullet.get("exploded", False)):
            new_bullets.append(bullet)

    room.bullets = new_bullets

    if wall_blocks_to_remove:
        grouped = defaultdict(list)
        for w_idx, b_idx in wall_blocks_to_remove:
            grouped[w_idx].append(b_idx)
        for w_idx, b_idxs in grouped.items():
            if 0 <= w_idx < len(room.walls):
                blocks = room.walls[w_idx]["blocks"]
                for b_idx in sorted(b_idxs, reverse=True):
                    if 0 <= b_idx < len(blocks):
                        blocks.pop(b_idx)
        room.walls = [w for w in room.walls if w["blocks"]]


def _track_missile(room: Room, bullet: dict):
    min_dist = None
    target_name = None
    for uname, p in room.players.items():
        if uname != bullet["owner"] and p["hp"] > 0:
            d = distance(p["x"], p["y"], bullet["x"], bullet["y"])
            if d <= cfg.MISSILE_TRACK_RANGE and (min_dist is None or d < min_dist):
                min_dist = d
                target_name = uname

    bullet["target"] = target_name
    if not target_name:
        return

    tx = room.players[target_name]["x"]
    ty = room.players[target_name]["y"]
    dx, dy = tx - bullet["x"], ty - bullet["y"]
    dist_to_target = math.hypot(dx, dy)
    if dist_to_target <= 0:
        return

    speed = math.hypot(bullet["dx"], bullet["dy"]) or 12
    cur_x, cur_y = bullet["dx"] / speed, bullet["dy"] / speed
    tgt_x, tgt_y = dx / dist_to_target, dy / dist_to_target
    alpha = 0.04
    new_x = (1 - alpha) * cur_x + alpha * tgt_x
    new_y = (1 - alpha) * cur_y + alpha * tgt_y
    norm = math.hypot(new_x, new_y) or 1
    bullet["dx"] = new_x / norm * speed
    bullet["dy"] = new_y / norm * speed


# ──────────────────────────────────────────────
#  Turrets
# ──────────────────────────────────────────────

def update_turrets(room: Room, now: float):
    updated = []
    for t in room.turrets:
        _decay_turret(t, now)
        if t.get("hp", 0) <= 0:
            continue

        target = _find_turret_target(room, t)
        if target and now - t.get("last_fire", 0) >= cfg.TURRET_FIRE_CD_SEC:
            _turret_fire(room, t, target)
            t["last_fire"] = now

        updated.append(t)
    room.turrets = updated


def _decay_turret(turret: dict, now: float):
    last_decay = turret.get("last_decay", turret.get("created_at", now))
    elapsed = max(0.0, now - last_decay)
    if elapsed > 0:
        turret["hp"] = max(0, turret.get("hp", 0) - cfg.TURRET_SELF_DECAY_PER_SEC * elapsed)
        turret["last_decay"] = now


def _find_turret_target(room: Room, turret: dict):
    tx, ty = turret["x"], turret["y"]
    min_d, target_pos = None, None

    for uname, p in room.players.items():
        if uname == turret.get("owner") or p["hp"] <= 0:
            continue
        d = math.hypot(p["x"] - tx, p["y"] - ty)
        if d <= cfg.TURRET_RANGE and (min_d is None or d < min_d):
            min_d, target_pos = d, (p["x"], p["y"])

    for other in room.turrets:
        if other is turret or other.get("owner") == turret.get("owner") or other.get("hp", 0) <= 0:
            continue
        d = math.hypot(other["x"] - tx, other["y"] - ty)
        if d <= cfg.TURRET_RANGE and (min_d is None or d < min_d):
            min_d, target_pos = d, (other["x"], other["y"])

    return target_pos


def _turret_fire(room: Room, turret: dict, target_pos: tuple):
    tx, ty = turret["x"], turret["y"]
    px, py = target_pos
    d = math.hypot(px - tx, py - ty) or 1
    room.bullets.append({
        "x": tx, "y": ty,
        "dx": (px - tx) / d * cfg.TURRET_BULLET_SPEED,
        "dy": (py - ty) / d * cfg.TURRET_BULLET_SPEED,
        "owner": turret.get("owner"),
        "hit_set": [],
        "start_x": tx, "start_y": ty,
        "max_dist": cfg.TURRET_MAX_DIST,
        "damage": cfg.TURRET_BULLET_DAMAGE,
        "created_at": time.time(),
        "type": "turret",
    })


# ──────────────────────────────────────────────
#  Bullet damage (players + turrets)
# ──────────────────────────────────────────────

def apply_bullet_damage(room: Room, now: float, users_db: dict) -> set:
    """Returns usernames of players that died this tick."""
    dead_players: set = set()
    bullets_to_remove: set = set()

    for username, player in room.players.items():
        for idx, bullet in enumerate(room.bullets):
            if player["hp"] <= 0 or username in dead_players:
                continue
            if bullet["owner"] == username or username in bullet.get("hit_set", []):
                continue
            d = distance(player["x"], player["y"], bullet["x"], bullet["y"])
            hit_r = cfg.MISSTLE_HIT_RADIUS if bullet.get("type") == "missile" else cfg.BULLET_HIT_RADIUS
            if d < hit_r:
                dmg = bullet.get("damage", cfg.BULLET_DEFAULT_DAMAGE)
                player["hp"] -= dmg
                player["last_hit"] = now
                bullet.setdefault("hit_set", []).append(username)
                if bullet["owner"] in users_db:
                    users_db[bullet["owner"]]["stats"]["total_damage"] += dmg
                if player["hp"] <= 0 and username not in dead_players:
                    dead_players.add(username)
                    player["deaths"] += 1
                    if bullet["owner"] in room.players:
                        room.players[bullet["owner"]]["kills"] += 1
                bullets_to_remove.add(idx)

    turret_remove: set = set()
    for t_idx, t in enumerate(room.turrets):
        if t.get("hp", 0) <= 0:
            turret_remove.add(t_idx)
            continue
        for idx, bullet in enumerate(room.bullets):
            if bullet.get("owner") == t.get("owner"):
                continue
            d = distance(t["x"], t["y"], bullet["x"], bullet["y"])
            hit_r = cfg.MISSTLE_HIT_RADIUS if bullet.get("type") == "missile" else cfg.BULLET_HIT_RADIUS
            if d < hit_r:
                t["hp"] = max(0, t["hp"] - bullet.get("damage", cfg.BULLET_DEFAULT_DAMAGE))
                bullets_to_remove.add(idx)
        if t.get("hp", 0) <= 0:
            turret_remove.add(t_idx)

    if turret_remove:
        room.turrets = [t for i, t in enumerate(room.turrets) if i not in turret_remove]
    if bullets_to_remove:
        room.bullets = [b for i, b in enumerate(room.bullets) if i not in bullets_to_remove]

    return dead_players


# ──────────────────────────────────────────────
#  Regeneration
# ──────────────────────────────────────────────

def update_regen(room: Room, now: float):
    for player in room.players.values():
        can_regen_dead = (
            "regen_when_dead" in player.get("perks", [])
            and getattr(cfg, "ALLOW_REGEN_WHEN_DEAD", True)
        )
        can_regen = (
            now - player["last_hit"] > cfg.REGEN_INTERVAL_SEC
            and player["hp"] < cfg.PLAYER_MAX_HP
            and (player["hp"] > 0 or can_regen_dead)
        )
        if can_regen:
            amount = cfg.REGEN_AMOUNT_PER_TICK
            if "regen_boost" in player.get("perks", []):
                amount *= 10
            player["hp"] += amount
        player["hp"] = min(player["hp"], cfg.PLAYER_MAX_HP)
        if player["hp"] <= 0:
            player["hp"] = 0


# ──────────────────────────────────────────────
#  Weapon cooldowns / iaido charges
# ──────────────────────────────────────────────

def update_weapon_state(room: Room, now: float, dt: float):
    for player in room.players.values():
        if player.get("active_weapon") != "iaido":
            player["iaido_charge_accum"] = 0.0
            continue

        charges = int(player.get("iaido_charges", 0))
        if charges >= cfg.IAIDO_CHARGE_MAX:
            player["iaido_charge_accum"] = 0.0
            continue

        interval = (
            cfg.IAIDO_CHARGE_INTERVAL_EMPTY_SEC
            if charges <= 0
            else cfg.IAIDO_CHARGE_INTERVAL_SEC
        )
        accum = float(player.get("iaido_charge_accum", 0.0)) + dt
        while charges < cfg.IAIDO_CHARGE_MAX and accum >= interval:
            charges += 1
            accum -= interval
            interval = (
                cfg.IAIDO_CHARGE_INTERVAL_EMPTY_SEC
                if charges <= 0
                else cfg.IAIDO_CHARGE_INTERVAL_SEC
            )
        player["iaido_charges"] = charges
        player["iaido_charge_accum"] = 0.0 if charges >= cfg.IAIDO_CHARGE_MAX else accum


# ──────────────────────────────────────────────
#  Composite tick + async game loop
# ──────────────────────────────────────────────

def update_room_tick(room: Room, now: float, users_db: dict, dt: float = 0.02) -> set:
    """Run all per-tick updates for one room. Returns dead-player usernames."""
    update_walls(room, now)
    update_smokes(room, now)
    update_cross_bombs(room, now)
    update_player_movement(room, now)
    update_bullets(room, now)
    update_turrets(room, now)
    update_weapon_state(room, now, dt)
    dead = apply_bullet_damage(room, now, users_db)
    update_regen(room, now)
    return dead


async def game_loop():
    from data_store import store
    tick_dt = 0.02

    while True:
        try:
            now = time.time()
            for room in list(store.rooms.values()):
                if not room.players:
                    continue

                dead = update_room_tick(room, now, store.users_db, tick_dt)

                for username in dead:
                    ws = room.connections.get(username)
                    if ws:
                        try:
                            await ws.send_text(
                                json.dumps({"type": "death", "message": "你已死亡! 按R重生"})
                            )
                        except Exception:
                            pass

                if room.connections:
                    state_msg = json.dumps(room.get_state())
                    for ws in list(room.connections.values()):
                        try:
                            await ws.send_text(state_msg)
                        except Exception:
                            pass

            await asyncio.sleep(tick_dt)
        except Exception as e:
            logger.error(f"Game loop error: {e}")
            await asyncio.sleep(1)
