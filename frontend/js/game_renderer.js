/**
 * GameRenderer — all Canvas 2D drawing in one cohesive class.
 *
 * Each public render*() method draws a single layer of the scene.
 * The top-level render() calls them in the correct z-order.
 */
class GameRenderer {

    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.turretAngles = new Map();
    }

    init(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
    }

    // ─── top-level render ─────────────────────────

    render(state, wm, isMouseDown, mousePos) {
        if (!this.ctx || !state) return;
        const c = this.canvas;
        this.ctx.clearRect(0, 0, c.width, c.height);

        const sx = c.width / CONFIG.MAP_WIDTH;
        const sy = c.height / CONFIG.MAP_HEIGHT;

        this.ctx.strokeStyle = "#ff0000";
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(0, 0, c.width, c.height);

        this.renderGraffiti(state, sx, sy);
        this.renderCrossBombs(state, sx, sy);
        this.renderPlayers(state, sx, sy, wm);
        this.renderWalls(state, sx, sy);
        this.renderTurrets(state, sx, sy);
        this.renderAimLine(state, sx, sy, wm, isMouseDown, mousePos);
        this.renderBullets(state, sx, sy);
        this.renderSmokes(state, sx, sy);
        this.renderUI(state, sx, sy, wm);
    }

    // ─── graffiti ─────────────────────────────────

    renderGraffiti(state, sx, sy) {
        if (!state.graffiti) return;
        if (!window.graffitiImg) {
            window.graffitiImg = new Image();
            window.graffitiImg.src = "res/graffiti/graffiti_default_0.png";
        }
        const img = window.graffitiImg;
        for (const [, g] of Object.entries(state.graffiti)) {
            const x = g.x * sx, y = g.y * sy, size = 60 * sx;
            if (img.complete) {
                this.ctx.save();
                this.ctx.globalAlpha = 0.95;
                this.ctx.drawImage(img, x - size / 2, y - size / 2, size, size);
                this.ctx.restore();
            }
        }
    }

    // ─── cross bombs ──────────────────────────────

    renderCrossBombs(state, sx, sy) {
        const bombs = state?.cross_bombs;
        if (!Array.isArray(bombs) || !bombs.length) return;
        const nowSec = Date.now() / 1000;
        const avg = (sx + sy) * 0.5;
        const armPx = (CONFIG.CROSS_BOMB_ARM_LENGTH || 300) * avg;
        const hwPx = ((CONFIG.CROSS_BOMB_ARM_WIDTH || 80) / 2) * avg;
        const fuseMs = CONFIG.CROSS_BOMB_FUSE_MS || 2000;
        const expMs = CONFIG.CROSS_BOMB_EXPLOSION_DURATION_MS || 600;
        const me = window.auth?.currentUser?.username;

        for (const b of bombs) {
            const bx = b.x * sx, by = b.y * sy;
            const angle = b.angle || 0;
            const owner = b.owner;
            const st = b.state || "armed";

            if (st === "armed") {
                this._drawArmedBomb(bx, by, angle, owner, me, b, nowSec, avg, armPx, hwPx, fuseMs);
            } else {
                this._drawDetonatingBomb(bx, by, angle, b, nowSec, avg, armPx, hwPx, expMs);
            }
        }
    }

    _drawArmedBomb(x, y, angle, owner, me, b, now, avg, armPx, hwPx, fuseMs) {
        const ctx = this.ctx;
        const plantedAt = b.planted_at || now;
        const explodeAt = b.explode_at || (plantedAt + fuseMs / 1000);
        const timeLeft = Math.max(0, (explodeAt - now) * 1000);
        const fuseRatio = fuseMs > 0 ? Math.min(1, timeLeft / fuseMs) : 0;
        const pulse = 0.7 + 0.3 * Math.sin((now - plantedAt) * 10);
        const base = 20 * avg * pulse;

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);

        ctx.fillStyle = owner === me ? "#ffe08a" : "#ff7272";
        ctx.strokeStyle = "#1d1d1d";
        ctx.lineWidth = Math.max(1.2, 2 * avg * 0.6);
        ctx.beginPath();
        ctx.rect(-base / 2, -base / 2, base, base);
        ctx.fill();
        ctx.stroke();

        const pAlpha = 0.45 + 0.35 * (1 - fuseRatio);
        const pLen = armPx;
        const pW = Math.max(3, hwPx * 2);
        ctx.globalAlpha = pAlpha;
        ctx.fillStyle = owner === me ? "#fff0b3" : "#ffbdbd";
        ctx.beginPath(); ctx.rect(-pLen, -pW / 2, pLen * 2, pW); ctx.fill();
        ctx.beginPath(); ctx.rect(-pW / 2, -pLen, pW, pLen * 2); ctx.fill();
        ctx.globalAlpha = 1;

        const bw = base * 0.9, bh = Math.max(3, base * 0.25);
        ctx.translate(0, -base * 0.9);
        ctx.fillStyle = "rgba(0,0,0,0.45)";
        ctx.fillRect(-bw / 2, -bh / 2, bw, bh);
        ctx.fillStyle = "#ffcc33";
        ctx.fillRect(-bw / 2, -bh / 2, bw * (1 - fuseRatio), bh);
        ctx.restore();
    }

    _drawDetonatingBomb(x, y, angle, b, now, avg, armPx, hwPx, expMs) {
        const ctx = this.ctx;
        const detTime = b.detonate_time || now;
        const elapsed = Math.max(0, (now - detTime) * 1000);
        if (elapsed > expMs) return;
        const prog = Math.min(1, elapsed / expMs);
        const alpha = Math.max(0, 0.75 * (1 - prog));
        const glow = Math.max(0, 0.6 * (1 - prog));

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        ctx.fillStyle = `rgba(255,220,120,${alpha.toFixed(3)})`;
        ctx.shadowColor = `rgba(255,180,60,${glow.toFixed(3)})`;
        ctx.shadowBlur = 28 * avg;
        ctx.beginPath(); ctx.rect(-armPx, -hwPx, armPx * 2, hwPx * 2); ctx.fill();
        ctx.beginPath(); ctx.rect(-hwPx, -armPx, hwPx * 2, armPx * 2); ctx.fill();
        ctx.restore();
    }

    // ─── players ──────────────────────────────────

    renderPlayers(state, sx, sy, wm) {
        const ctx = this.ctx;
        const me = window.auth.currentUser.username;

        for (const [uname, p] of Object.entries(state.players)) {
            const x = p.x * sx, y = p.y * sy, r = CONFIG.PLAYER_RADIUS * sx;

            ctx.beginPath();
            ctx.arc(x, y, r, 0, 2 * Math.PI);
            ctx.fillStyle = p.status === "dead" ? "#666" : (uname === me ? "#ffff00" : "#ff4444");
            ctx.fill();
            ctx.strokeStyle = "#222";
            ctx.stroke();

            ctx.font = "12px Arial"; ctx.fillStyle = "#fff"; ctx.textAlign = "center";
            ctx.fillText(uname, x, y - r - 5);

            if (p.status === "alive") {
                const bw = r * 2, bh = 8;
                ctx.fillStyle = "#222"; ctx.fillRect(x - bw / 2, y + r + 5, bw, bh);
                ctx.fillStyle = "#ff4444"; ctx.fillRect(x - bw / 2, y + r + 5, bw * (p.hp / CONFIG.MAX_HP), bh);
                ctx.font = "10px Arial"; ctx.fillStyle = "#fff"; ctx.fillText(p.hp, x, y + r + 15);

                if (uname === me && wm.weaponType === "iaido") {
                    this._drawIaidoChargeBar(x, y, r, bw, bh, wm);
                }
            } else {
                ctx.font = "10px Arial"; ctx.fillStyle = "#ff4444"; ctx.fillText("DEAD", x, y + r + 10);
            }

            if (p.kills > 0) {
                ctx.font = "10px Arial"; ctx.fillStyle = "#ffff00"; ctx.fillText(`Kills: ${p.kills}`, x, y - r - 15);
            }

            if (uname === me) {
                if (wm.shootCD > 0) {
                    ctx.font = "16px Arial"; ctx.fillStyle = "#ff4444"; ctx.textAlign = "center";
                    ctx.fillText((wm.shootCD / 1000).toFixed(1), x, y + 5);
                }
                if (p.status === "dead") {
                    ctx.font = "24px Arial"; ctx.fillStyle = "#ff4444"; ctx.textAlign = "center";
                    ctx.fillText("你已死亡! 按R键复活", this.canvas.width / 2, this.canvas.height / 2);
                }
            }
        }
    }

    _drawIaidoChargeBar(x, y, r, bw, bh, wm) {
        const ctx = this.ctx;
        const slots = CONFIG.IAIDO_CHARGE_MAX || 3;
        const filled = Math.max(0, Math.min(slots, wm.iaidoCharges));
        const gap = 2;
        const segW = (bw - (slots - 1) * gap) / slots;
        const segH = 8;
        const cy = y + r + 5 + bh + 4;

        ctx.save();
        ctx.strokeStyle = "#999"; ctx.lineWidth = 1;
        for (let i = 0; i < slots; i++) {
            const bx = x - bw / 2 + i * (segW + gap);
            ctx.strokeRect(bx, cy, segW, segH);
            if (i < filled) {
                ctx.fillStyle = "#66ccff";
                ctx.fillRect(bx + 1, cy + 1, segW - 2, segH - 2);
            } else if (i === filled && filled < slots) {
                const ratio = Math.min(1, wm.iaidoChargeProgress || 0);
                ctx.fillStyle = "#66ccff80";
                ctx.fillRect(bx + 1, cy + 1, (segW - 2) * ratio, segH - 2);
            }
        }
        ctx.restore();
    }

    // ─── walls ────────────────────────────────────

    renderWalls(state, sx, sy) {
        if (!state?.walls) return;
        const ctx = this.ctx;
        for (const wall of state.walls) {
            for (const block of wall.blocks) {
                const bx = block.x * sx, by = block.y * sy, size = (CONFIG.WALL_BLOCK_SIZE || 32) * sx;
                ctx.save();
                ctx.fillStyle = "#888"; ctx.strokeStyle = "#222"; ctx.globalAlpha = 0.85;
                ctx.fillRect(bx - size / 2, by - size / 2, size, size);
                ctx.strokeRect(bx - size / 2, by - size / 2, size, size);
                ctx.restore();
            }
        }
    }

    // ─── turrets ──────────────────────────────────

    renderTurrets(state, sx, sy) {
        if (!state?.turrets) return;
        const ctx = this.ctx;
        const me = window.auth.currentUser.username;
        const range = CONFIG.TURRET_RANGE || 300;

        for (const t of state.turrets) {
            const x = t.x * sx, y = t.y * sy, size = 36 * sx;
            const isMe = t.owner === me;
            this._drawTurretBase(x, y, size, isMe);
            this._drawTurretBarrel(x, y, size, t, state, sx, sy, range);

            const bw = size * 1.3, bh = 6, barY = y + size / 2 + 8;
            ctx.fillStyle = "#222"; ctx.fillRect(x - bw / 2, barY, bw, bh);
            ctx.fillStyle = "#ff4444"; ctx.fillRect(x - bw / 2, barY, bw * (t.hp / CONFIG.TURRET_HP), bh);

            ctx.save();
            ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
            const nf = Math.max(10, Math.floor(size * 0.33));
            ctx.font = `${nf}px Arial`;
            ctx.lineWidth = Math.max(1, Math.floor(nf * 0.18));
            ctx.strokeStyle = "rgba(0,0,0,0.7)"; ctx.fillStyle = "#ffffff";
            const ny = y - size / 2 - 6;
            try { ctx.strokeText(t.owner, x, ny); } catch (_) {}
            ctx.fillText(t.owner, x, ny);
            ctx.restore();
        }
    }

    _drawTurretBase(x, y, size, isMe) {
        const ctx = this.ctx;
        const r = size / 2;
        ctx.save();

        const og = ctx.createRadialGradient(x, y, r * 0.2, x, y, r);
        if (isMe) { og.addColorStop(0, "#fff7a0"); og.addColorStop(0.65, "#ffe453"); og.addColorStop(1, "#c7a400"); }
        else { og.addColorStop(0, "#ffb3b3"); og.addColorStop(0.65, "#ff6b6b"); og.addColorStop(1, "#a82323"); }
        ctx.fillStyle = og;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();

        ctx.lineWidth = Math.max(2, r * 0.08); ctx.strokeStyle = "#222"; ctx.stroke();
        ctx.save(); ctx.globalAlpha = 0.25;
        ctx.beginPath(); ctx.ellipse(x + r * 0.08, y + r * 0.18, r * 0.95, r * 0.55, 0, 0, 2 * Math.PI);
        ctx.fillStyle = "#000"; ctx.fill(); ctx.restore();

        const cr = r * 0.68;
        const cg = ctx.createLinearGradient(x - cr, y - cr, x + cr, y + cr);
        cg.addColorStop(0, "#666"); cg.addColorStop(0.5, "#bbb"); cg.addColorStop(1, "#444");
        ctx.beginPath(); ctx.arc(x, y, cr, 0, 2 * Math.PI);
        ctx.fillStyle = cg; ctx.fill();
        ctx.strokeStyle = "#111"; ctx.lineWidth = Math.max(1, r * 0.05); ctx.stroke();

        ctx.beginPath(); ctx.arc(x, y, cr * 0.92, -2.5, -0.5, false);
        ctx.strokeStyle = "rgba(255,255,255,0.65)"; ctx.lineWidth = Math.max(1, r * 0.06); ctx.stroke();

        const rc = 6, rr = Math.max(1.8, r * 0.09), ro = r * 0.82;
        for (let i = 0; i < rc; i++) {
            const a = (i / rc) * Math.PI * 2;
            const rx = x + Math.cos(a) * ro, ry = y + Math.sin(a) * ro;
            const rg = ctx.createRadialGradient(rx, ry, 0, rx, ry, rr);
            rg.addColorStop(0, "#eee"); rg.addColorStop(0.6, "#bbb"); rg.addColorStop(1, "#666");
            ctx.beginPath(); ctx.arc(rx, ry, rr, 0, 2 * Math.PI);
            ctx.fillStyle = rg; ctx.fill();
            ctx.strokeStyle = "#222"; ctx.lineWidth = Math.max(0.8, r * 0.03); ctx.stroke();
        }
        ctx.restore();
    }

    _drawTurretBarrel(x, y, size, t, state, sx, sy, range) {
        const ctx = this.ctx;
        let targetScreen = null, bestDist = Infinity;
        if (state?.players) {
            for (const [u, p] of Object.entries(state.players)) {
                if (u === t.owner || p.status !== "alive") continue;
                const dm = Math.hypot(p.x - t.x, p.y - t.y);
                if (dm <= range && dm < bestDist) { bestDist = dm; targetScreen = { x: p.x * sx, y: p.y * sy }; }
            }
        }
        if (state?.turrets) {
            for (const o of state.turrets) {
                if (o.owner === t.owner || !o.hp || o.hp <= 0) continue;
                if (o.x === t.x && o.y === t.y && o.owner === t.owner) continue;
                const dm = Math.hypot(o.x - t.x, o.y - t.y);
                if (dm <= range && dm < bestDist) { bestDist = dm; targetScreen = { x: o.x * sx, y: o.y * sy }; }
            }
        }

        const key = `${t.owner}|${t.x}|${t.y}`;
        const hasPrev = this.turretAngles.has(key);
        const prev = hasPrev ? this.turretAngles.get(key) : 0;
        const desired = targetScreen ? Math.atan2(targetScreen.y - y, targetScreen.x - x) : 0;
        let delta = desired - prev;
        while (delta > Math.PI) delta -= Math.PI * 2;
        while (delta < -Math.PI) delta += Math.PI * 2;
        const alpha = 0.18;
        let angle = hasPrev ? (prev + delta * alpha) : desired;
        if (Math.abs(delta) < 0.002) angle = desired;
        this.turretAngles.set(key, angle);

        const bLen = Math.max(size * 0.9, 18), bW = Math.max(size * 0.22, 6);
        ctx.save();
        ctx.translate(x, y); ctx.rotate(angle);

        const bg = ctx.createLinearGradient(0, 0, bLen, 0);
        bg.addColorStop(0, "#cfcfcf"); bg.addColorStop(0.45, "#9a9a9a"); bg.addColorStop(0.55, "#e9e9e9"); bg.addColorStop(1, "#888888");
        ctx.beginPath(); ctx.rect(0, -bW / 2, bLen, bW);
        ctx.fillStyle = bg; ctx.strokeStyle = "#222"; ctx.lineWidth = 2; ctx.fill(); ctx.stroke();

        ctx.beginPath(); ctx.rect(bLen * 0.15, -bW * 0.28, bLen * 0.55, bW * 0.16);
        ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.fill();

        const capR = bW * 0.25;
        const cg = ctx.createRadialGradient(bLen, 0, 0, bLen, 0, capR);
        cg.addColorStop(0, "#ffffff"); cg.addColorStop(0.5, "#cfcfcf"); cg.addColorStop(1, "#7a7a7a");
        ctx.beginPath(); ctx.arc(bLen, 0, capR, 0, 2 * Math.PI);
        ctx.fillStyle = cg; ctx.fill();
        ctx.restore();
    }

    // ─── bullets ──────────────────────────────────

    renderBullets(state, sx, sy) {
        const ctx = this.ctx;
        const me = window.auth.currentUser.username;
        for (const b of state.bullets || []) {
            const x = b.x * sx, y = b.y * sy;
            let r = CONFIG.BULLET_RADIUS * sx;
            const color = b.owner === me ? "#ffff00" : "#ff4444";

            if (b.type === "missile") { this._drawMissile(x, y, b, r, sx, color); continue; }
            if (b.type === "turret")  { this._drawTurretBullet(x, y, r, sx, color); continue; }

            ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color; ctx.fill();
        }
    }

    _drawMissile(x, y, b, baseR, sx, color) {
        const ctx = this.ctx;
        const r = baseR * 2.2;
        const tailLen = 50 * sx;
        let vx = b.vx ?? b.dx ?? 0, vy = b.vy ?? b.dy ?? 0;
        const vlen = Math.hypot(vx, vy);
        if (vlen > 0) { vx /= vlen; vy /= vlen; }
        const angle = Math.atan2(vy, vx);
        const now = Date.now();

        ctx.save();
        ctx.translate(x, y); ctx.rotate(angle); ctx.translate(-r * 0.8, 0);
        const fw = r * (1.1 + 0.4 * Math.sin(now / 80 + x + y));
        const fl = tailLen * (0.95 + 0.15 * Math.sin(now / 120 + x));
        const fr = (Math.random() - 0.5) * fw * 0.2;
        ctx.beginPath(); ctx.moveTo(-fl, 0);
        ctx.bezierCurveTo(-fl * 0.7, -fw + fr, -fl * 0.3, -fw * 0.7 + fr, 0, -fw * 0.3);
        ctx.lineTo(0, fw * 0.3);
        ctx.bezierCurveTo(-fl * 0.3, fw * 0.7 + fr, -fl * 0.7, fw + fr, -fl, 0);
        ctx.closePath();
        const fg = ctx.createLinearGradient(-fl, 0, 0, 0);
        fg.addColorStop(0, "#ff3300"); fg.addColorStop(0.5, "#ff9900"); fg.addColorStop(1, "#ffff00");
        ctx.globalAlpha = 0.7; ctx.fillStyle = fg; ctx.fill(); ctx.globalAlpha = 1;
        ctx.restore();

        ctx.save();
        ctx.translate(x, y); ctx.rotate(angle);
        ctx.beginPath(); ctx.ellipse(0, 0, r * 1.6, r * 0.7, 0, 0, 2 * Math.PI);
        ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 12 * sx; ctx.fill();
        ctx.beginPath(); ctx.moveTo(r * 1.6, 0); ctx.lineTo(r * 0.8, r * 0.5); ctx.lineTo(r * 0.8, -r * 0.5); ctx.closePath();
        ctx.fillStyle = "#fff"; ctx.fill();
        ctx.beginPath(); ctx.moveTo(-r * 1.2, -r * 0.5); ctx.lineTo(-r * 2.0, -r * 1.0); ctx.lineTo(-r * 1.4, 0);
        ctx.lineTo(-r * 2.0, r * 1.0); ctx.lineTo(-r * 1.2, r * 0.5); ctx.closePath();
        ctx.fillStyle = "#888"; ctx.fill();
        ctx.restore();
    }

    _drawTurretBullet(x, y, baseR, sx, color) {
        const ctx = this.ctx;
        const bodyR = Math.max(baseR * 0.9, 2.2 * sx);
        const g = ctx.createRadialGradient(x, y, 0, x, y, bodyR);
        g.addColorStop(0, "#ffffff"); g.addColorStop(0.45, "#cfcfcf"); g.addColorStop(0.75, "#8f8f8f"); g.addColorStop(1, "#6a6a6a");
        ctx.beginPath(); ctx.arc(x, y, bodyR, 0, 2 * Math.PI);
        ctx.fillStyle = g; ctx.shadowColor = color; ctx.shadowBlur = 5 * sx; ctx.fill();
        ctx.shadowBlur = 0; ctx.strokeStyle = "#222"; ctx.lineWidth = 1.0 * sx; ctx.stroke();
    }

    // ─── smokes ───────────────────────────────────

    renderSmokes(state, sx, sy) {
        if (!state.smokes) return;
        const ctx = this.ctx;
        const me = window.auth.currentUser.username;
        const now = Date.now();

        for (const s of state.smokes) {
            const x = s.x * sx, y = s.y * sy;
            const ar = (s.current_radius || 0) * sx;
            const isOwn = s.owner === me;
            const edgeColor = isOwn ? "#ffff00" : "#ff4444";

            ctx.save();
            ctx.globalAlpha = isOwn ? 0.3 : 1.0;
            ctx.beginPath(); ctx.arc(x, y, Math.max(0, ar * 0.99), 0, 2 * Math.PI); ctx.closePath();
            ctx.fillStyle = "#888"; ctx.fill();

            const steps = 60;
            ctx.globalAlpha = 1;
            ctx.beginPath();
            for (let i = 0; i <= steps; i++) {
                const a = (2 * Math.PI / steps) * i;
                const rO = ar * (1 + 0.012 * Math.sin(now / 180 + a * 6 + x + y));
                if (i === 0) ctx.moveTo(x + Math.cos(a) * rO, y + Math.sin(a) * rO);
                else ctx.lineTo(x + Math.cos(a) * rO, y + Math.sin(a) * rO);
            }
            for (let i = steps; i >= 0; i--) {
                const a = (2 * Math.PI / steps) * i;
                const rI = ar * 0.99 * (1 + 0.012 * Math.cos(now / 220 + a * 7 + x - y));
                ctx.lineTo(x + Math.cos(a) * rI, y + Math.sin(a) * rI);
            }
            ctx.closePath();
            ctx.fillStyle = edgeColor; ctx.fill();
            ctx.restore();
        }
    }

    // ─── aim line / weapon preview ────────────────

    renderAimLine(state, sx, sy, wm, isMouseDown, mousePos) {
        if (!isMouseDown || !mousePos) return;
        const me = state?.players?.[window.auth.currentUser.username];
        if (!me || me.status !== "alive") return;

        const ctx = this.ctx;
        const meX = me.x * sx, meY = me.y * sy;
        let dx = mousePos.x - meX, dy = mousePos.y - meY;
        const len = Math.hypot(dx, dy);
        if (len <= 0) return;

        ctx.save();
        ctx.strokeStyle = wm.shootCD > 0 ? "rgba(255,0,0,0.2)" : "rgba(255,255,255,0.3)";
        ctx.lineWidth = 30 * sx;

        const wt = wm.weaponType;
        if (wt === "shotgun")        this._aimShotgun(ctx, meX, meY, dx, dy, sx);
        else if (wt === "missile")   this._aimLine(ctx, meX, meY, dx, dy, len, CONFIG.MISSILE_RANGE * sx);
        else if (wt === "wall")      this._aimWall(ctx, state, me, sx, sy, mousePos);
        else if (wt === "smoke")     this._aimSmoke(ctx, me, sx, sy, mousePos);
        else if (wt === "turret")    this._aimTurret(ctx, me, sx, sy, mousePos);
        else if (wt === "iaido")     this._aimIaido(ctx, meX, meY, dx, dy, sx, wm);
        else if (wt === "crossbomb") this._aimLine(ctx, meX, meY, dx, dy, len, (CONFIG.CROSS_BOMB_MAX_DISTANCE || 540) * sx);
        else                         this._aimLine(ctx, meX, meY, dx, dy, len, CONFIG.BULLET_RANGE * sx);

        ctx.restore();
    }

    _aimLine(ctx, meX, meY, dx, dy, len, maxDist) {
        const ndx = dx / len * maxDist, ndy = dy / len * maxDist;
        ctx.beginPath(); ctx.moveTo(meX, meY); ctx.lineTo(meX + ndx, meY + ndy); ctx.stroke();
    }

    _aimShotgun(ctx, meX, meY, dx, dy, sx) {
        const maxDist = CONFIG.SHOTGUN_RANGE * sx;
        const base = Math.atan2(dy, dx);
        const spread = Math.PI / 6;
        ctx.beginPath(); ctx.moveTo(meX, meY);
        for (let i = 0; i <= 30; i++) {
            const a = base - spread / 2 + (spread / 30) * i;
            ctx.lineTo(meX + Math.cos(a) * maxDist, meY + Math.sin(a) * maxDist);
        }
        ctx.closePath();
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fill();
    }

    _aimWall(ctx, state, me, sx, sy, mousePos) {
        const mapMX = mousePos.x / sx, mapMY = mousePos.y / sy;
        const px = me.x, py = me.y;
        let ddx = mapMX - px, ddy = mapMY - py;
        const maxD = 400, d = Math.hypot(ddx, ddy);
        let tx = mapMX, ty = mapMY;
        if (d > maxD && d > 0) { const r = maxD / d; tx = px + ddx * r; ty = py + ddy * r; }
        const angle = Math.abs(Math.atan2(ty - py, tx - px));
        const blocks = [];
        if (angle < Math.PI / 4 || angle > 3 * Math.PI / 4)
            for (let i = -4; i < 4; i++) blocks.push({ x: tx, y: ty + i * 32 });
        else
            for (let i = -4; i < 4; i++) blocks.push({ x: tx + i * 32, y: ty });

        ctx.save();
        ctx.beginPath(); ctx.arc(px * sx, py * sy, maxD * sx, 0, 2 * Math.PI);
        ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.lineWidth = 2; ctx.setLineDash([8, 8]); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();

        let overlap = false;
        const pR = (CONFIG.PLAYER_RADIUS || 32) + 24;
        for (const b of blocks) {
            for (const [, p] of Object.entries(state.players)) {
                if (p.status !== "alive") continue;
                if (Math.hypot(b.x - p.x, b.y - p.y) < pR) { overlap = true; break; }
            }
            if (overlap) break;
        }
        const bs = 32 * sx;
        for (const b of blocks) {
            ctx.fillStyle = overlap ? "rgba(255,0,0,0.2)" : ctx.strokeStyle;
            ctx.fillRect(b.x * sx - bs / 2, b.y * sy - bs / 2, bs, bs);
        }
    }

    _aimSmoke(ctx, me, sx, sy, mousePos) {
        const mapMX = mousePos.x / sx, mapMY = mousePos.y / sy;
        const maxD = 400;
        let ddx = mapMX - me.x, ddy = mapMY - me.y, d = Math.hypot(ddx, ddy);
        let px, py;
        if (d <= maxD) { px = mousePos.x; py = mousePos.y; }
        else { const r = maxD / d; px = (me.x + ddx * r) * sx; py = (me.y + ddy * r) * sy; }

        ctx.save(); ctx.globalAlpha = 1;
        ctx.beginPath(); ctx.arc(px, py, 180 * sx, 0, 2 * Math.PI); ctx.closePath();
        ctx.fillStyle = ctx.strokeStyle; ctx.fill();

        ctx.beginPath(); ctx.arc(me.x * sx, me.y * sy, maxD * sx, 0, 2 * Math.PI);
        ctx.strokeStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.setLineDash([8, 8]); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();
    }

    _aimTurret(ctx, me, sx, sy, mousePos) {
        const mapMX = mousePos.x / sx, mapMY = mousePos.y / sy;
        const limit = CONFIG.TURRET_PLACE_RANGE;
        let ddx = mapMX - me.x, ddy = mapMY - me.y, d = Math.hypot(ddx, ddy);
        let tx = mapMX, ty = mapMY;
        if (d > limit && d > 0) { const r = limit / d; tx = me.x + ddx * r; ty = me.y + ddy * r; }
        const px = tx * sx, py = ty * sy;
        const baseSize = 36 * sx;
        const tRange = CONFIG.TURRET_RANGE * sx;
        const limitPx = limit * sx;
        const meXpx = me.x * sx, meYpx = me.y * sy;

        ctx.save();
        ctx.beginPath(); ctx.arc(px, py, tRange, 0, 2 * Math.PI);
        ctx.strokeStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.setLineDash([8, 8]); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();

        ctx.save(); ctx.globalAlpha = 0.6;
        ctx.beginPath(); ctx.arc(px, py, baseSize / 2, 0, 2 * Math.PI); ctx.closePath();
        ctx.fillStyle = ctx.strokeStyle; ctx.fill();
        ctx.restore();

        ctx.save();
        ctx.beginPath(); ctx.arc(meXpx, meYpx, limitPx, 0, 2 * Math.PI);
        ctx.strokeStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.setLineDash([6, 6]); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();
    }

    _aimIaido(ctx, meX, meY, dx, dy, sx, wm) {
        let maxDistRaw = CONFIG.IAIDO_DISTANCE;
        if (typeof wm.iaidoHoldStart === "number") {
            const held = Math.max(0, Date.now() - wm.iaidoHoldStart);
            const t = Math.min(1, held / (CONFIG.IAIDO_HOLD_MAX_MS || 800));
            const minD = CONFIG.IAIDO_MIN_DISTANCE || Math.min(120, CONFIG.IAIDO_DISTANCE);
            maxDistRaw = minD + (CONFIG.IAIDO_DISTANCE - minD) * t;
        }
        const maxDist = maxDistRaw * sx;
        const base = Math.atan2(dy, dx);
        ctx.strokeStyle = wm.iaidoCharges < 1 ? "rgba(255,0,0,0.2)" : "rgba(255,255,255,0.3)";
        ctx.beginPath(); ctx.moveTo(meX, meY);
        ctx.lineTo(meX + Math.cos(base) * maxDist, meY + Math.sin(base) * maxDist);
        ctx.lineWidth = CONFIG.IAIDO_WIDTH * sx;
        ctx.stroke();
    }

    // ─── HUD overlay ──────────────────────────────

    renderUI(state, sx, sy, wm) {
        const me = state?.players?.[window.auth.currentUser.username];
        if (!me) return;
        const ctx = this.ctx;

        const weaponName = wm.getDisplayName();
        ctx.font = "14px Arial"; ctx.fillStyle = "#fff"; ctx.textAlign = "left";
        const slots = window.auth?.currentUser?.loadout?.weapon_slots;
        const slotText = (Array.isArray(slots) && slots.length >= 4)
            ? `槽位: [1:${slots[0]} 2:${slots[1]} 3:${slots[2]} 4:${slots[3]}]`
            : "数字键1~7切换";
        ctx.fillText(`武器: ${weaponName} (${slotText})`, 20, 30);

        if (wm.switchWeaponCD > 0) {
            ctx.font = "13px Arial"; ctx.fillStyle = "#ff9900"; ctx.textAlign = "left";
            ctx.fillText(`武器切换CD: ${(wm.switchWeaponCD / 1000).toFixed(1)}s`, 20, 52);
        }
    }
}

window.GameRenderer = GameRenderer;
