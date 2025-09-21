class Game {

    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.lastState = null;
        this.shootCD = 0;
        this.switchWeaponCD = 0;
        this.isMouseDown = false;
        this.mousePos = null;
        this.pressedKeys = new Set();
        this.wsManager = null;
        this.weaponType = "single"; // "single" 单发, "shotgun" 散弹, "missile" 追踪导弹, "wall" 建墙, "smoke" 烟雾弹

        this.initCDTimer();
    }

    init(canvas, wsManager) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.wsManager = wsManager;
        this.setupControls();
    }

    setupControls() {
        // 鼠标控制
        this.canvas.addEventListener("mousedown", (e) => this.onMouseDown(e));
        this.canvas.addEventListener("mousemove", (e) => this.onMouseMove(e));
        this.canvas.addEventListener("mouseup", (e) => this.onMouseUp(e));

        // 键盘控制
        document.addEventListener("keydown", (e) => this.onKeyDown(e));
        document.addEventListener("keyup", (e) => this.onKeyUp(e));
    }

    onMouseDown(e) {
        this.isMouseDown = true;
        const rect = this.canvas.getBoundingClientRect();
        this.mousePos = { 
            x: e.clientX - rect.left, 
            y: e.clientY - rect.top 
        };
    }

    onMouseMove(e) {
        if (this.isMouseDown) {
            const rect = this.canvas.getBoundingClientRect();
            this.mousePos = { 
                x: e.clientX - rect.left, 
                y: e.clientY - rect.top 
            };
        }
    }

    onMouseUp(e) {
        if (this.shootCD > 0) {
            this.isMouseDown = false;
            this.mousePos = null;
            this.render();
            return;
        }

        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const me = this.lastState?.players?.[window.auth.currentUser.username];
        if (!me || me.status !== 'alive') {
            this.isMouseDown = false;
            this.mousePos = null;
            return;
        }

        if (this.weaponType === "single") {
            this.shootSingle(me, mouseX, mouseY);
        } else if (this.weaponType === "shotgun") {
            this.shootShotgun(me, mouseX, mouseY);
        } else if (this.weaponType === "missile") {
            this.shootMissile(me, mouseX, mouseY);
        } else if (this.weaponType === "wall") {
            this.buildWall(mouseX, mouseY);
        } else if (this.weaponType === "smoke") {
            this.throwSmoke(me, mouseX, mouseY);
        } else if (this.weaponType === "turret") {
            this.summonTurret(mouseX, mouseY);
        }

        this.isMouseDown = false;
        this.mousePos = null;
    }

    throwSmoke(me, mouseX, mouseY) {
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        // 地图坐标
        const mapMouseX = mouseX * scaleX;
        const mapMouseY = mouseY * scaleY;
        const mapMeX = me.x;
        const mapMeY = me.y;
        let dx = mapMouseX - mapMeX;
        let dy = mapMouseY - mapMeY;
        let dist = Math.hypot(dx, dy);
        const maxThrowDist = 400; // 最大距离

        let targetX, targetY;
        if (dist <= maxThrowDist) {
            targetX = mapMouseX;
            targetY = mapMouseY;
        } else {
            // 计算交点
            let ratio = maxThrowDist / dist;
            targetX = mapMeX + dx * ratio;
            targetY = mapMeY + dy * ratio;
        }

        this.wsManager.sendMessage({
            type: "smoke_grenade",
            x: targetX,
            y: targetY,
            radius: 180,
            duration: 15
        });
        this.shootCD = 5000;
    }

    shootMissile(me, mouseX, mouseY) {
        // 计算射击方向
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        let dx = (mouseX * scaleX) - me.x;
        let dy = (mouseY * scaleY) - me.y;
        let len = Math.sqrt(dx*dx + dy*dy);
        if (len === 0) return;
        // 限制射击距离
        if (len > CONFIG.MISSILE_RANGE) {
            dx = dx / len * CONFIG.MISSILE_RANGE;
            dy = dy / len * CONFIG.MISSILE_RANGE;
            len = CONFIG.MISSILE_RANGE;
        }
        // 归一化速度
        dx = dx / len * CONFIG.MISSILE_SPEED;
        dy = dy / len * CONFIG.MISSILE_SPEED;
        // 发送导弹发射消息
        this.wsManager.sendMessage({
            type: "shoot_missile",
            dx: dx,
            dy: dy,
            max_dist: CONFIG.MISSILE_RANGE,
            damage: CONFIG.MISSILE_DAMAGE
        });
        this.shootCD = CONFIG.MISSILE_CD;
    }

    shootSingle(me, mouseX, mouseY) {
        // 计算射击方向
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        let dx = (mouseX * scaleX) - me.x;
        let dy = (mouseY * scaleY) - me.y;
        let len = Math.sqrt(dx*dx + dy*dy);
        if (len === 0) return;
        // 限制射击距离
        if (len > CONFIG.BULLET_RANGE) {
            dx = dx / len * CONFIG.BULLET_RANGE;
            dy = dy / len * CONFIG.BULLET_RANGE;
            len = CONFIG.BULLET_RANGE;
        }
        // 归一化速度
        dx = dx / len * CONFIG.BULLET_SPEED;
        dy = dy / len * CONFIG.BULLET_SPEED;

        this.wsManager.sendMessage({
            type: "shoot",
            dx: dx,
            dy: dy,
            max_dist: CONFIG.BULLET_RANGE,
            damage: CONFIG.BULLET_DAMAGE
        });

        this.shootCD = CONFIG.BULLET_CD;
    }

    shootShotgun(me, mouseX, mouseY) {
        // 计算射击方向
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        let dx = (mouseX * scaleX) - me.x;
        let dy = (mouseY * scaleY) - me.y;
        let len = Math.sqrt(dx*dx + dy*dy);
        if (len === 0) return;
        // 限制射击距离
        if (len > CONFIG.SHOTGUN_RANGE) {
            dx = dx / len * CONFIG.SHOTGUN_RANGE;
            dy = dy / len * CONFIG.SHOTGUN_RANGE;
            len = CONFIG.SHOTGUN_RANGE;
        }
        // 归一化速度
        dx = dx / len * CONFIG.SHOTGUN_SPEED;
        dy = dy / len * CONFIG.SHOTGUN_SPEED;
        // 散弹：发射多颗子弹，角度有偏移
        const bulletCount = 6; // 散弹数量
        const spread = Math.PI / 6; // 总散布角度（弧度）
        const baseAngle = Math.atan2(dy, dx);
        for (let i = 0; i < bulletCount; i++) {
            // -spread/2 到 +spread/2
            const angle = baseAngle - spread/2 + (spread/(bulletCount-1))*i;
            const ddx = Math.cos(angle) * CONFIG.SHOTGUN_SPEED;
            const ddy = Math.sin(angle) * CONFIG.SHOTGUN_SPEED;
            // 显式传递 damage 字段
            this.wsManager.sendMessage({
                type: "shoot",
                dx: ddx,
                dy: ddy,
                max_dist: CONFIG.SHOTGUN_RANGE,
                damage: CONFIG.SHOTGUN_DAMAGE
            });
        }
        this.shootCD = CONFIG.SHOTGUN_CD;
    }

    buildWall(mouseX, mouseY) {
        // 建墙武器，先判断预览方块是否与玩家重叠
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        const me = this.lastState?.players?.[window.auth.currentUser.username];
        const mapMouseX = mouseX * scaleX;
        const mapMouseY = mouseY * scaleY;
        const px = me.x, py = me.y;
        const dx = mapMouseX - px;
        const dy = mapMouseY - py;
        let angle = Math.abs(Math.atan2(dy, dx));
        let blocks = [];
        if (angle < Math.PI/4 || angle > 3*Math.PI/4) {
            // 竖墙
            for (let i = -4; i < 4; i++) {
                blocks.push({x: mapMouseX, y: mapMouseY + i * 32});
            }
        } else {
            // 横墙
            for (let i = -4; i < 4; i++) {
                blocks.push({x: mapMouseX + i * 32, y: mapMouseY});
            }
        }
        // 距离限制
        const maxBuildDist = 400;
        const distToMe = Math.hypot(mapMouseX - px, mapMouseY - py);
        if (distToMe > maxBuildDist) {
            window.ui && window.ui.showTip && window.ui.showTip("掩体距离过远，无法建造！");
            this.isMouseDown = false;
            this.mousePos = null;
            this.render();
            return;
        }
        // 检查是否有玩家重叠
        let overlap = false;
        const playerRadius = (CONFIG.PLAYER_RADIUS || 32) + 24;
        for (const block of blocks) {
            for (const [uname, player] of Object.entries(this.lastState.players)) {
                if (player.status !== 'alive') continue;
                const dist = Math.hypot(block.x - player.x, block.y - player.y);
                if (dist < playerRadius) {
                    overlap = true;
                    break;
                }
            }
            if (overlap) break;
        }
        if (overlap) {
            window.ui && window.ui.showTip && window.ui.showTip("掩体位置有玩家，无法建造！");
            this.isMouseDown = false;
            this.mousePos = null;
            this.render();
            return;
        }
        // 没有重叠且距离合规才发送建墙消息
        this.wsManager.sendMessage({
            type: "build_wall",
            x: mouseX,
            y: mouseY
        });
        this.shootCD = CONFIG.WALL_CD;
    }

    summonTurret(mouseX, mouseY) {
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        const me = this.lastState?.players?.[window.auth.currentUser.username];
        if (!me) return;
        const mapMeX = me.x;
        const mapMeY = me.y;
        const mapMouseX = mouseX * scaleX;
        const mapMouseY = mouseY * scaleY;
        let dx = mapMouseX - mapMeX;
        let dy = mapMouseY - mapMeY;
        let dist = Math.hypot(dx, dy);
        const limit = (CONFIG.TURRET_PLACE_RANGE || 150);
        let targetX = mapMouseX;
        let targetY = mapMouseY;
        if (dist > limit && dist > 0) {
            const ratio = limit / dist;
            targetX = mapMeX + dx * ratio;
            targetY = mapMeY + dy * ratio;
        }
        this.wsManager.sendMessage({
            type: "summon_turret",
            x: targetX,
            y: targetY
        });
        this.shootCD = 4000;
    }

    onKeyDown(e) {
        const key = e.key.toLowerCase();
        if (key === "r") {
            this.wsManager.respawn();
        } else if (["w", "s", "a", "d", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) {
            this.pressedKeys.add(key);
            this.updateDirection();
        } else if (["1", "2", "3", "4", "5", "6"].includes(key)) {
            let newType = "single";
            if (key === "2") newType = "shotgun";
            else if (key === "3") newType = "missile";
            else if (key === "4") newType = "wall";
            else if (key === "5") newType = "smoke";
            else if (key === "6") newType = "turret";
            if (this.weaponType === newType) {
                window.ui && window.ui.showTip && window.ui.showTip(`已是${newType === "single" ? "单发" : newType === "shotgun" ? "散弹" : newType === "missile" ? "追踪导弹" : "建墙"}武器`);
                return;
            }
            if (this.switchWeaponCD > 0) {
                window.ui && window.ui.showTip && window.ui.showTip("武器切换冷却中...");
                return;
            }
            this.weaponType = newType;
            window.ui && window.ui.showTip && window.ui.showTip(`武器切换为：${newType === "single" ? "单发" : newType === "shotgun" ? "散弹" : newType === "missile" ? "追踪导弹" : newType === "wall" ? "建墙" : newType === "smoke" ? "烟雾弹" : newType === "turret" ? "炮台" : newType}`);
            this.switchWeaponCD = CONFIG.SWITCH_WEAPON_CD;
        } else if (key === "x") {
            // 涂鸦：在当前位置留下涂鸦
            const me = this.lastState?.players?.[window.auth.currentUser.username];
            if (me && me.status === 'alive') {
                this.wsManager.sendMessage({
                    type: "graffiti",
                    x: me.x,
                    y: me.y
                });
            }
        }
    }

    onKeyUp(e) {
        const key = e.key.toLowerCase();
        if (["w", "s", "a", "d", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) {
            this.pressedKeys.delete(key);
            this.updateDirection();
        }
    }
    

    render() {
        if (!this.ctx || !this.lastState) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const scaleX = this.canvas.width / CONFIG.MAP_WIDTH;
        const scaleY = this.canvas.height / CONFIG.MAP_HEIGHT;

        this.ctx.strokeStyle = "#ff0000";
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(0, 0, this.canvas.width, this.canvas.height);

        this.renderGraffiti(scaleX, scaleY);
        this.renderPlayers(scaleX, scaleY);
    this.renderWalls(scaleX, scaleY);
    this.renderTurrets(scaleX, scaleY);
        this.renderAimLine(scaleX, scaleY);
        this.renderBullets(scaleX, scaleY);
        this.renderSmokes(scaleX, scaleY);
        this.renderUI(scaleX, scaleY);
    }

    renderSmokes(scaleX, scaleY) {
        if (!this.lastState.smokes) return;
        const me = window.auth.currentUser.username;
        const now = Date.now();
        for (const smoke of this.lastState.smokes) {
            const x = smoke.x * scaleX;
            const y = smoke.y * scaleY;

            const animRadius = (smoke.current_radius || 0) * scaleX;

            this.ctx.save();
            // 设置边框颜色
            let edgeColor = smoke.owner === me ? "#ffff00" : "#ff4444";
            // 设置透明度
            let mainAlpha = smoke.owner === me ? 0.3 : 1.0;
            this.ctx.globalAlpha = mainAlpha;
            this.ctx.beginPath();
            this.ctx.arc(x, y, Math.max(0, animRadius * 0.99), 0, 2 * Math.PI);
            this.ctx.closePath();
            this.ctx.fillStyle = "#888";
            this.ctx.fill();

            // 边缘一圈流动效果
            let edgeSteps = 60;
            this.ctx.globalAlpha = 1;
            this.ctx.beginPath();
            for (let i = 0; i <= edgeSteps; i++) {
                let angle = (2 * Math.PI / edgeSteps) * i;
                // 边缘半径动态扰动，流动感
                let rOuter = animRadius * (1 + 0.012 * Math.sin(now/180 + angle*6 + x + y));
                let rInner = animRadius * 0.99 * (1 + 0.012 * Math.cos(now/220 + angle*7 + x - y));
                if (i === 0) {
                    this.ctx.moveTo(x + Math.cos(angle) * rOuter, y + Math.sin(angle) * rOuter);
                } else {
                    this.ctx.lineTo(x + Math.cos(angle) * rOuter, y + Math.sin(angle) * rOuter);
                }
            }
            for (let i = edgeSteps; i >= 0; i--) {
                let angle = (2 * Math.PI / edgeSteps) * i;
                let rInner = animRadius * 0.99 * (1 + 0.012 * Math.cos(now/220 + angle*7 + x - y));
                this.ctx.lineTo(x + Math.cos(angle) * rInner, y + Math.sin(angle) * rInner);
            }
            this.ctx.closePath();
            this.ctx.fillStyle = edgeColor;
            this.ctx.fill();
            this.ctx.restore();
        }
    }

    renderGraffiti(scaleX, scaleY) {
        if (!this.lastState.graffiti) return;
        if (!window.graffitiImg) {
            window.graffitiImg = new Image();
            window.graffitiImg.src = "res/graffiti/graffiti_default_0.png";
        }
        const img = window.graffitiImg;
        for (const [username, g] of Object.entries(this.lastState.graffiti)) {
            const x = g.x * scaleX;
            const y = g.y * scaleY;
            const size = 60 * scaleX;
            if (img.complete) {
                this.ctx.save();
                this.ctx.globalAlpha = 0.95;
                this.ctx.drawImage(img, x - size/2, y - size/2, size, size);
                this.ctx.restore();
            }
        }
    }

    renderWalls(scaleX, scaleY) {
        if (!this.lastState?.walls) return;
        for (const wall of this.lastState.walls) {
            for (const block of wall.blocks) {
                const bx = block.x * scaleX;
                const by = block.y * scaleY;
                const size = 32 * scaleX;
                this.ctx.save();
                this.ctx.fillStyle = "#888";
                this.ctx.strokeStyle = "#222";
                this.ctx.globalAlpha = 0.85;
                this.ctx.fillRect(bx - size/2, by - size/2, size, size);
                this.ctx.strokeRect(bx - size/2, by - size/2, size, size);
                this.ctx.restore();
            }
        }
    }

    renderTurrets(scaleX, scaleY) {
        if (!this.lastState?.turrets) return;
        for (const t of this.lastState.turrets) {
            const x = t.x * scaleX;
            const y = t.y * scaleY;
            const size = 36 * scaleX;
            // 底座与炮管简化显示
            this.ctx.save();
            this.ctx.fillStyle = t.owner === window.auth.currentUser.username ? "#66ccff" : "#ff8844";
            this.ctx.strokeStyle = "#222";
            this.ctx.globalAlpha = 0.95;
            this.ctx.beginPath();
            this.ctx.arc(x, y, size/2, 0, 2*Math.PI);
            this.ctx.fill();
            this.ctx.stroke();
            this.ctx.restore();
            // 血条
            const barWidth = size * 1.3;
            const barHeight = 6;
            this.ctx.fillStyle = "#222";
            this.ctx.fillRect(x - barWidth/2, y - size/2 - 12, barWidth, barHeight);
            this.ctx.fillStyle = "#44ff44";
            this.ctx.fillRect(x - barWidth/2, y - size/2 - 12, barWidth * (t.hp / 300), barHeight);
        }
    }

    renderBullets(scaleX, scaleY) {
        for (const bullet of this.lastState.bullets || []) {
            const x = bullet.x * scaleX;
            const y = bullet.y * scaleY;
            let radius = CONFIG.BULLET_RADIUS * scaleX;
            let color = bullet.owner === window.auth.currentUser.username ? "#ffff00" : "#ff4444";
            // 导弹特殊显示
            if (bullet.type === "missile") {
                radius = CONFIG.BULLET_RADIUS * 2.2 * scaleX;
                // 拖尾特效参数
                const tailLen = 50 * scaleX;
                // 计算速度方向（需服务端同步提供 vx/vy，否则用 dx/dy 或上帧位置）
                let vx = bullet.vx ?? bullet.dx ?? 0;
                let vy = bullet.vy ?? bullet.dy ?? 0;
                let vlen = Math.sqrt(vx*vx + vy*vy);
                if (vlen > 0) {
                    vx /= vlen;
                    vy /= vlen;
                }
                // 拖尾起点
                const tx = x - vx * tailLen;
                const ty = y - vy * tailLen;
                // 计算角度
                var angle = Math.atan2(vy, vx);
                // 绘制火焰拖尾（整体往后移，避免被火箭遮挡）
                this.ctx.save();
                this.ctx.translate(x, y);
                this.ctx.rotate(angle);
                // 往后移一段距离（如火箭长度的 80%）
                this.ctx.translate(-radius * 0.8, 0);
                // 动态火焰形状参数
                const now = Date.now();
                // 让火焰宽度和波动随时间变化
                const flameW = radius * (1.1 + 0.4 * Math.sin(now/80 + x + y));
                const flameL = tailLen * (0.95 + 0.15 * Math.sin(now/120 + x));
                // 随机扰动火焰顶点，模拟跳动
                const flameRand = (Math.random() - 0.5) * flameW * 0.2;
                this.ctx.beginPath();
                this.ctx.moveTo(-flameL, 0);
                this.ctx.bezierCurveTo(-flameL * 0.7, -flameW + flameRand, -flameL * 0.3, -flameW * 0.7 + flameRand, 0, -flameW * 0.3);
                this.ctx.lineTo(0, flameW * 0.3);
                this.ctx.bezierCurveTo(-flameL * 0.3, flameW * 0.7 + flameRand, -flameL * 0.7, flameW + flameRand, -flameL, 0);
                this.ctx.closePath();
                // 渐变填充火焰
                const flameGrad = this.ctx.createLinearGradient(-flameL, 0, 0, 0);
                flameGrad.addColorStop(0, "#ff3300"); // 深红
                flameGrad.addColorStop(0.5, "#ff9900"); // 橙色
                flameGrad.addColorStop(1, "#ffff00"); // 黄色
                this.ctx.globalAlpha = 0.7;
                this.ctx.fillStyle = flameGrad;
                this.ctx.fill();
                this.ctx.globalAlpha = 1;
                this.ctx.restore();
                // 绘制火箭弹体（主轴与飞行方向一致）
                this.ctx.save();
                this.ctx.translate(x, y);
                this.ctx.rotate(angle);
                // 主体（火箭身，长轴为x方向）
                this.ctx.beginPath();
                this.ctx.ellipse(0, 0, radius * 1.6, radius * 0.7, 0, 0, 2 * Math.PI);
                this.ctx.fillStyle = color;
                this.ctx.shadowColor = color;
                this.ctx.shadowBlur = 12 * scaleX;
                this.ctx.fill();
                // 火箭头部（x轴正方向）
                this.ctx.beginPath();
                this.ctx.moveTo(radius * 1.6, 0);
                this.ctx.lineTo(radius * 0.8, radius * 0.5);
                this.ctx.lineTo(radius * 0.8, -radius * 0.5);
                this.ctx.closePath();
                this.ctx.fillStyle = '#fff';
                this.ctx.fill();
                // 火箭尾翼（x轴负方向）
                this.ctx.beginPath();
                this.ctx.moveTo(-radius * 1.2, -radius * 0.5);
                this.ctx.lineTo(-radius * 2.0, -radius * 1.0);
                this.ctx.lineTo(-radius * 1.4, 0);
                this.ctx.lineTo(-radius * 2.0, radius * 1.0);
                this.ctx.lineTo(-radius * 1.2, radius * 0.5);
                this.ctx.closePath();
                this.ctx.fillStyle = '#888';
                this.ctx.fill();
                this.ctx.restore();
                continue;
            }
            // 普通子弹
            this.ctx.beginPath();
            this.ctx.arc(x, y, radius, 0, 2 * Math.PI);
            this.ctx.fillStyle = color;
            this.ctx.fill();
        }
    }

    updateDirection() {
        let dx = 0, dy = 0;
        if (this.pressedKeys.has("w") || this.pressedKeys.has("arrowup")) dy -= CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("s") || this.pressedKeys.has("arrowdown")) dy += CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("a") || this.pressedKeys.has("arrowleft")) dx -= CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("d") || this.pressedKeys.has("arrowright")) dx += CONFIG.PLAYER_SPEED;
        // 斜向归一化
        if (dx !== 0 && dy !== 0) {
            const norm = Math.sqrt(2);
            dx /= norm;
            dy /= norm;
        }
        this.wsManager.move(dx, dy);
    }

    renderPlayers(scaleX, scaleY) {
        for (const [username, player] of Object.entries(this.lastState.players)) {
            const x = player.x * scaleX;
            const y = player.y * scaleY;
            const radius = CONFIG.PLAYER_RADIUS * scaleX;
            this.ctx.beginPath();
            this.ctx.arc(x, y, radius, 0, 2 * Math.PI);
            if (player.status === 'dead') {
                this.ctx.fillStyle = "#666";
            } else if (username === window.auth.currentUser.username) {
                this.ctx.fillStyle = "#ffff00"; // 自己黄色
            } else {
                this.ctx.fillStyle = "#ff4444"; // 敌人红色
            }
            this.ctx.fill();
            this.ctx.strokeStyle = "#222";
            this.ctx.stroke();
            this.ctx.font = "12px Arial";
            this.ctx.fillStyle = "#fff";
            this.ctx.textAlign = "center";
            this.ctx.fillText(username, x, y - radius - 5);
            if (player.status === 'alive') {
                const barWidth = radius * 2;
                const barHeight = 8;
                this.ctx.fillStyle = "#222";
                this.ctx.fillRect(x - barWidth/2, y + radius + 5, barWidth, barHeight);
                this.ctx.fillStyle = "#ff4444";
                this.ctx.fillRect(x - barWidth/2, y + radius + 5, barWidth * (player.hp / CONFIG.MAX_HP), barHeight);
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#fff";
                this.ctx.fillText(player.hp, x, y + radius + 15);
            } else {
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#ff4444";
                this.ctx.fillText("DEAD", x, y + radius + 10);
            }
            if (player.kills > 0) {
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#ffff00";
                this.ctx.fillText(`Kills: ${player.kills}`, x, y - radius - 15);
            }

            // 仅为当前玩家显示CD和死亡提示
            if (username === window.auth.currentUser.username) {
                if (this.shootCD > 0) {
                    this.ctx.font = "16px Arial";
                    this.ctx.fillStyle = "#ff4444";
                    this.ctx.textAlign = "center";
                    this.ctx.fillText((this.shootCD / 1000).toFixed(1), x, y + 5);
                }
                if (player.status === 'dead') {
                    this.ctx.font = "24px Arial";
                    this.ctx.fillStyle = "#ff4444";
                    this.ctx.textAlign = "center";
                    this.ctx.fillText("你已死亡! 按R键复活", this.canvas.width / 2, this.canvas.height / 2);
                }
            }
        }
    }

    renderAimLine(scaleX, scaleY) {
        if (this.isMouseDown && this.mousePos) {
            const me = this.lastState?.players?.[window.auth.currentUser.username];
            if (me && me.status === 'alive') {
                const meX = me.x * scaleX;
                const meY = me.y * scaleY;
                let dx = this.mousePos.x - meX;
                let dy = this.mousePos.y - meY;
                let len = Math.sqrt(dx*dx + dy*dy);
                if (len > 0) {
                    this.ctx.save();
                    this.ctx.strokeStyle = this.shootCD > 0 ? "rgba(255,0,0,0.2)" : "rgba(255,255,255,0.3)";
                    this.ctx.lineWidth = 30 * scaleX;


                    if (this.weaponType === "shotgun") {
                        const maxDist = CONFIG.SHOTGUN_RANGE * scaleX;
                        const baseAngle = Math.atan2(dy, dx);
                        const spread = Math.PI / 6;
                        const arcSteps = 30;
                        this.ctx.beginPath();
                        this.ctx.moveTo(meX, meY);
                        for (let i = 0; i <= arcSteps; i++) {
                            const angle = baseAngle - spread/2 + (spread/arcSteps)*i;
                            const tx = meX + Math.cos(angle) * maxDist;
                            const ty = meY + Math.sin(angle) * maxDist;
                            this.ctx.lineTo(tx, ty);
                        }
                        this.ctx.closePath();
                        // cd没好红色，cd好白色
                        this.ctx.fillStyle = this.ctx.strokeStyle;

                        this.ctx.fill();


                    } else if (this.weaponType === "missile") {
                        // 导弹瞄准线无限距离
                        const maxDist = CONFIG.MISSILE_RANGE * scaleX;
                        dx = dx / len * maxDist;
                        dy = dy / len * maxDist;
                        const tx = meX + dx;
                        const ty = meY + dy;
                        this.ctx.beginPath();
                        this.ctx.moveTo(meX, meY);
                        this.ctx.lineTo(tx, ty);
                        this.ctx.stroke();


                    } else if (this.weaponType === "wall") {
                        // 掩体预览渲染
                        const blockSize = 32 * scaleX;
                        // 转为地图坐标
                        const mapMouseX = this.mousePos.x / scaleX;
                        const mapMouseY = this.mousePos.y / scaleY;
                        const mapMeX = me.x;
                        const mapMeY = me.y;
                        const ddx = mapMouseX - mapMeX;
                        const ddy = mapMouseY - mapMeY;
                        let angle = Math.abs(Math.atan2(ddy, ddx));
                        let blocks = [];
                        if (angle < Math.PI/4 || angle > 3*Math.PI/4) {
                            // 竖墙
                            for (let i = -4; i < 4; i++) {
                                blocks.push({x: mapMouseX, y: mapMouseY + i * 32});
                            }
                        } else {
                            // 横墙
                            for (let i = -4; i < 4; i++) {
                                blocks.push({x: mapMouseX + i * 32, y: mapMouseY});
                            }
                        }
                        // 距离限制
                        const maxBuildDist = 400;
                        const distToMe = Math.hypot(mapMouseX - mapMeX, mapMouseY - mapMeY);
                        // 渲染建造距离圆形范围
                        this.ctx.save();
                        this.ctx.beginPath();
                        this.ctx.arc(mapMeX * scaleX, mapMeY * scaleY, maxBuildDist * scaleX, 0, 2 * Math.PI);
                        this.ctx.strokeStyle = "rgba(255,255,255,0.25)";
                        this.ctx.lineWidth = 2;
                        this.ctx.setLineDash([8, 8]);
                        this.ctx.stroke();
                        this.ctx.setLineDash([]);
                        this.ctx.restore();
                        // 检查是否有玩家重叠
                        let overlap = false;
                        const playerRadius = (CONFIG.PLAYER_RADIUS || 32) + 24;
                        for (const block of blocks) {
                            for (const [uname, player] of Object.entries(this.lastState.players)) {
                                if (player.status !== 'alive') continue;
                                const dist = Math.hypot(block.x - player.x, block.y - player.y);
                                if (dist < playerRadius) {
                                    overlap = true;
                                    break;
                                }
                            }
                            if (overlap) break;
                        }
                        // 渲染预览
                        let canBuild = distToMe <= maxBuildDist && !overlap;
                        for (const block of blocks) {
                            const bx = block.x * scaleX;
                            const by = block.y * scaleY;
                            this.ctx.fillStyle = canBuild ? this.ctx.strokeStyle : "rgba(255,0,0,0.2)";
                            this.ctx.fillRect(bx - blockSize/2, by - blockSize/2, blockSize, blockSize);
                        }
                        
                    } else if (this.weaponType === "smoke") {
                        // 烟雾弹预览渲染
                        const smokeRadius = 180 * scaleX; // 与后端最大半径一致
                        const maxThrowDist = 400; // 最远释放距离
                        const mapMouseX = this.mousePos.x / scaleX;
                        const mapMouseY = this.mousePos.y / scaleY;
                        const mapMeX = me.x;
                        const mapMeY = me.y;
                        let dx = mapMouseX - mapMeX;
                        let dy = mapMouseY - mapMeY;
                        let dist = Math.hypot(dx, dy);

                        // 计算预览圆心
                        let previewX, previewY;
                        let canThrow = (dist <= maxThrowDist);
                        if (canThrow) {
                            previewX = this.mousePos.x;
                            previewY = this.mousePos.y;
                        } else {
                            // 计算交点
                            let ratio = maxThrowDist / dist;
                            let targetMapX = mapMeX + dx * ratio;
                            let targetMapY = mapMeY + dy * ratio;
                            previewX = targetMapX * scaleX;
                            previewY = targetMapY * scaleY;
                        }
                        
                        const previewAlpha = 1;
                        this.ctx.save();
                        this.ctx.globalAlpha = previewAlpha;
                        this.ctx.beginPath();
                        this.ctx.arc(previewX, previewY, smokeRadius, 0, 2 * Math.PI);
                        this.ctx.closePath();
                        this.ctx.fillStyle = this.ctx.strokeStyle;
                        this.ctx.fill();

                        this.ctx.save();
                        this.ctx.beginPath();
                        this.ctx.arc(mapMeX * scaleX, mapMeY * scaleY, maxThrowDist * scaleX, 0, 2 * Math.PI);
                        this.ctx.strokeStyle = this.ctx.strokeStyle;
                        this.ctx.lineWidth = 2;
                        this.ctx.setLineDash([8, 8]);
                        this.ctx.stroke();
                        this.ctx.setLineDash([]);
                        this.ctx.restore();

                    } else if (this.weaponType === "turret") {
                        // 炮台预览渲染：底座与攻击范围，并限制距离（超距拉回）
                        const mapMouseX = this.mousePos.x / scaleX;
                        const mapMouseY = this.mousePos.y / scaleY;
                        const mapMeX = me.x;
                        const mapMeY = me.y;
                        let ddx = mapMouseX - mapMeX;
                        let ddy = mapMouseY - mapMeY;
                        let d = Math.hypot(ddx, ddy);
                        const placeLimit = (CONFIG.TURRET_PLACE_RANGE || 150);
                        let targetMapX = mapMouseX;
                        let targetMapY = mapMouseY;
                        if (d > placeLimit && d > 0) {
                            const ratio = placeLimit / d;
                            targetMapX = mapMeX + ddx * ratio;
                            targetMapY = mapMeY + ddy * ratio;
                        }
                        const previewX = targetMapX * scaleX;
                        const previewY = targetMapY * scaleY;
                        const baseSize = 36 * scaleX; // 与渲染一致
                        const turretRange = 600 * scaleX; // 服务端 TURRET_RANGE = 600
                        const placeLimitPx = placeLimit * scaleX;
                        const meXMap = me.x * scaleX;
                        const meYMap = me.y * scaleY;
                        const placeDist = Math.hypot(previewX - meXMap, previewY - meYMap);

                        // 攻击范围环（以预览位置为圆心）
                        this.ctx.save();
                        this.ctx.beginPath();
                        this.ctx.arc(previewX, previewY, turretRange, 0, 2 * Math.PI);
                        this.ctx.strokeStyle = this.ctx.strokeStyle;
                        this.ctx.lineWidth = 2;
                        this.ctx.setLineDash([8, 8]);
                        this.ctx.stroke();
                        this.ctx.setLineDash([]);
                        this.ctx.restore();

                        // 炮台底座圆
                        this.ctx.save();
                        this.ctx.globalAlpha = 0.6;
                        this.ctx.beginPath();
                        this.ctx.arc(previewX, previewY, baseSize / 2, 0, 2 * Math.PI);
                        this.ctx.closePath();
                        this.ctx.fillStyle = this.ctx.strokeStyle
                        this.ctx.fill();
                        this.ctx.restore();

                        // 玩家放置范围圈
                        this.ctx.save();
                        this.ctx.beginPath();
                        this.ctx.arc(meXMap, meYMap, placeLimitPx, 0, 2 * Math.PI);
                        this.ctx.strokeStyle = this.ctx.strokeStyle;
                        this.ctx.lineWidth = 2;
                        this.ctx.setLineDash([6, 6]);
                        this.ctx.stroke();
                        this.ctx.setLineDash([]);
                        this.ctx.restore();

                    } else {
                        // 单发枪为直线
                        const maxDist = CONFIG.BULLET_RANGE * scaleX;
                        dx = dx / len * maxDist;
                        dy = dy / len * maxDist;
                        const tx = meX + dx;
                        const ty = meY + dy;
                        this.ctx.beginPath();
                        this.ctx.moveTo(meX, meY);
                        this.ctx.lineTo(tx, ty);
                        this.ctx.stroke();
                    }
                    this.ctx.restore();
                }
            }
        }
    }

    // 冷却计时器方法，确保在类内部
    initCDTimer() {
        setInterval(() => {
            if (this.shootCD > 0) {
                this.shootCD -= 100;
                if (this.shootCD < 0) this.shootCD = 0;
            }
            if (this.switchWeaponCD > 0) {
                this.switchWeaponCD -= 100;
                if (this.switchWeaponCD < 0) this.switchWeaponCD = 0;
            }
        }, 100);
    }

    updateState(state) {
        this.lastState = state;
        this.render();
        if (state.room_info) {
            window.ui.updateRoomInfo(state.room_info);
        }
    }

    renderUI(scaleX, scaleY) {
        const me = this.lastState?.players?.[window.auth.currentUser.username];
        if (!me) return;
        const meX = me.x * scaleX;
        const meY = me.y * scaleY;
        
        // 显示武器类型
        let weaponName = "单发步枪";
        if (this.weaponType === "shotgun") weaponName = "霰弹";
        else if (this.weaponType === "missile") weaponName = "追踪导弹";
        else if (this.weaponType === "wall") weaponName = "掩体";
    else if (this.weaponType === "smoke") weaponName = "烟雾弹";
    else if (this.weaponType === "turret") weaponName = "炮台";
        this.ctx.font = "14px Arial";
        this.ctx.fillStyle = "#fff";
        this.ctx.textAlign = "left";
    this.ctx.fillText(`武器: ${weaponName} (数字键1~6切换)`, 20, 30);
        // 显示武器切换冷却
        if (this.switchWeaponCD > 0) {
            this.ctx.font = "13px Arial";
            this.ctx.fillStyle = "#ff9900";
            this.ctx.textAlign = "left";
            this.ctx.fillText(`武器切换CD: ${(this.switchWeaponCD / 1000).toFixed(1)}s`, 20, 52);
        }
    }

}

window.Game = Game;