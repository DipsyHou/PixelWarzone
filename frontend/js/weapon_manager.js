/**
 * WeaponManager — client-side input + optimistic UI only.
 *
 * Combat numbers and cooldowns are authoritative on the server.
 * This class sends fire / switch intents and mirrors server state for HUD.
 */
class WeaponManager {

    constructor() {
        this.weaponType = "single";
        this.shootCD = 0;
        this.switchWeaponCD = 0;
        this.iaidoCharges = 0;
        this.iaidoChargeProgress = 0;
        this.iaidoHoldStart = undefined;
    }

    initFromLoadout() {
        try {
            const slots = window.auth?.currentUser?.loadout?.weapon_slots;
            const allowed = [
                "single", "shotgun", "missile", "wall",
                "smoke", "turret", "iaido", "crossbomb",
            ];
            if (Array.isArray(slots) && slots[0] && allowed.includes(slots[0])) {
                this.weaponType = slots[0];
            } else {
                this.weaponType = "single";
            }
        } catch (_) {
            this.weaponType = "single";
        }
    }

    /** Sync HUD timers / charges from authoritative player state. */
    syncFromPlayer(me) {
        if (!me) return;
        if (me.active_weapon) this.weaponType = me.active_weapon;
        if (typeof me.weapon_cd_ms === "number") this.shootCD = me.weapon_cd_ms;
        if (typeof me.switch_cd_ms === "number") this.switchWeaponCD = me.switch_cd_ms;
        if (typeof me.iaido_charges === "number") this.iaidoCharges = me.iaido_charges;
        if (typeof me.iaido_charge_progress === "number") {
            this.iaidoChargeProgress = me.iaido_charge_progress;
        }
    }

    getDisplayName(type) {
        const names = {
            single: "单发步枪", shotgun: "霰弹", missile: "追踪导弹",
            wall: "掩体投放", smoke: "烟雾弹", turret: "部署炮台",
            iaido: "居合", crossbomb: "十字炸弹",
        };
        return names[type || this.weaponType] || type || "未知";
    }

    switchWeapon(key) {
        let newType = null;
        const loadout = window.auth?.currentUser?.loadout;
        if (["1", "2", "3", "4"].includes(key) && loadout && Array.isArray(loadout.weapon_slots)) {
            newType = loadout.weapon_slots[parseInt(key, 10) - 1] || null;
        }
        if (["5", "6", "7"].includes(key)) return false;

        if (!newType) {
            const defaults = {
                "1": "single", "2": "shotgun", "3": "missile", "4": "wall",
                "5": "smoke", "6": "turret", "7": "iaido",
            };
            newType = defaults[key] || "single";
        }

        if (this.weaponType === newType) {
            window.ui?.showTip?.(`已是${this.getDisplayName(newType)}`);
            return false;
        }
        if (this.switchWeaponCD > 0) {
            window.ui?.showTip?.("武器切换冷却中...");
            return false;
        }

        this.weaponType = newType;
        window.ui?.showTip?.(`武器切换为：${this.getDisplayName(newType)}`);
        // Optimistic local CD; server will confirm via state
        this.switchWeaponCD = CONFIG.SWITCH_WEAPON_CD || 3000;

        if (window.wsManager) {
            window.wsManager.sendMessage({ type: "switch_weapon", weapon: newType });
        }
        return true;
    }

    fire(me, mouseX, mouseY, canvas, wsManager, lastState) {
        if (this.weaponType !== "iaido" && this.shootCD > 0) return;

        const m = this._toMap(mouseX, mouseY, canvas);
        const msg = {
            type: "fire",
            aim_x: m.x,
            aim_y: m.y,
            dirx: m.x - me.x,
            diry: m.y - me.y,
        };

        if (this.weaponType === "iaido") {
            if (this.iaidoCharges < 1) {
                window.ui?.showTip?.("居合无充能");
                return;
            }
            if (typeof this.iaidoHoldStart === "number") {
                msg.hold_ms = Math.max(0, Date.now() - this.iaidoHoldStart);
            } else {
                msg.hold_ms = 0;
            }
            // Optimistic charge spend
            this.iaidoCharges = Math.max(0, this.iaidoCharges - 1);
        } else {
            // Optimistic local CD from server-published config
            const cdKey = {
                single: "BULLET_CD",
                shotgun: "SHOTGUN_CD",
                missile: "MISSILE_CD",
                wall: "WALL_CD",
                smoke: "SMOKE_CD",
                turret: "TURRET_CD",
                crossbomb: "CROSS_BOMB_CD",
            }[this.weaponType];
            if (cdKey && CONFIG[cdKey]) this.shootCD = CONFIG[cdKey];
        }

        // Soft client-side wall occupancy check (server also rejects)
        if (this.weaponType === "wall" && lastState) {
            const maxDist = CONFIG.WALL_PLACE_RANGE || 400;
            let tx = m.x, ty = m.y;
            const dist = Math.hypot(m.x - me.x, m.y - me.y);
            if (dist > maxDist && dist > 0) {
                const r = maxDist / dist;
                tx = me.x + (m.x - me.x) * r;
                ty = me.y + (m.y - me.y) * r;
            }
            const angle = Math.abs(Math.atan2(ty - me.y, tx - me.x));
            const bs = CONFIG.WALL_BLOCK_SIZE || 32;
            const blocks = [];
            if (angle < Math.PI / 4 || angle > 3 * Math.PI / 4) {
                for (let i = -4; i < 4; i++) blocks.push({ x: tx, y: ty + i * bs });
            } else {
                for (let i = -4; i < 4; i++) blocks.push({ x: tx + i * bs, y: ty });
            }
            const pRadius = (CONFIG.PLAYER_RADIUS || 32) + 24;
            for (const b of blocks) {
                for (const [, pl] of Object.entries(lastState.players || {})) {
                    if (pl.status !== "alive") continue;
                    if (Math.hypot(b.x - pl.x, b.y - pl.y) < pRadius) {
                        window.ui?.showTip?.("掩体位置有玩家，无法建造！");
                        return;
                    }
                }
            }
        }

        wsManager.sendMessage(msg);
    }

    _toMap(mouseX, mouseY, canvas) {
        return {
            x: mouseX * (CONFIG.MAP_WIDTH / canvas.width),
            y: mouseY * (CONFIG.MAP_HEIGHT / canvas.height),
        };
    }
}

window.WeaponManager = WeaponManager;
