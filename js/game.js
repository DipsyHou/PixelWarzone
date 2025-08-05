class Game {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.lastState = null;
        this.shootCD = 0;
        this.isMouseDown = false;
        this.mousePos = null;
        this.pressedKeys = new Set();
        this.wsManager = null;
        
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

        // 计算射击方向
        const scaleX = CONFIG.MAP_WIDTH / this.canvas.width;
        const scaleY = CONFIG.MAP_HEIGHT / this.canvas.height;
        
        let dx = (mouseX * scaleX) - me.x;
        let dy = (mouseY * scaleY) - me.y;
        let len = Math.sqrt(dx*dx + dy*dy);
        
        if (len === 0) {
            this.isMouseDown = false;
            this.mousePos = null;
            return;
        }

        // 限制射击距离
        if (len > CONFIG.MAX_BULLET_DIST) {
            dx = dx / len * CONFIG.MAX_BULLET_DIST;
            dy = dy / len * CONFIG.MAX_BULLET_DIST;
            len = CONFIG.MAX_BULLET_DIST;
        }

        // 归一化速度
        dx = dx / len * CONFIG.BULLET_SPEED;
        dy = dy / len * CONFIG.BULLET_SPEED;

        if (this.wsManager.shoot(dx, dy)) {
            this.shootCD = CONFIG.SHOOT_CD;
        }

        this.isMouseDown = false;
        this.mousePos = null;
    }

    onKeyDown(e) {
        const key = e.key.toLowerCase();
        
        if (key === "r") {
            this.wsManager.respawn();
        } else if (["w", "s", "a", "d", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) {
            this.pressedKeys.add(key);
            this.updateDirection();
        }
    }

    onKeyUp(e) {
        const key = e.key.toLowerCase();
        if (["w", "s", "a", "d", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) {
            this.pressedKeys.delete(key);
            this.updateDirection();
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

    updateState(state) {
        this.lastState = state;
        this.render();
        
        // 更新房间信息
        if (state.room_info) {
            window.ui.updateRoomInfo(state.room_info);
        }
    }

    render() {
        if (!this.ctx || !this.lastState) return;
        
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const scaleX = this.canvas.width / CONFIG.MAP_WIDTH;
        const scaleY = this.canvas.height / CONFIG.MAP_HEIGHT;

        // 地图边界
        this.ctx.strokeStyle = "#ff0000";
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(0, 0, this.canvas.width, this.canvas.height);

        // 渲染玩家
        this.renderPlayers(scaleX, scaleY);
        
        // 渲染瞄准线
        this.renderAimLine(scaleX, scaleY);
        
        // 渲染子弹
        this.renderBullets(scaleX, scaleY);
        
        // 渲染UI
        this.renderUI(scaleX, scaleY);
    }

    renderPlayers(scaleX, scaleY) {
        for (const [username, player] of Object.entries(this.lastState.players)) {
            const x = player.x * scaleX;
            const y = player.y * scaleY;
            const radius = CONFIG.PLAYER_RADIUS * scaleX;
            
            // 玩家圆形
            this.ctx.beginPath();
            this.ctx.arc(x, y, radius, 0, 2 * Math.PI);
            
            if (player.status === 'dead') {
                this.ctx.fillStyle = "#666";
            } else {
                this.ctx.fillStyle = username === window.auth.currentUser.username ? "#00ff00" : "#0000ff";
            }
            this.ctx.fill();
            this.ctx.strokeStyle = "#222";
            this.ctx.stroke();

            // 玩家名
            this.ctx.font = "12px Arial";
            this.ctx.fillStyle = "#fff";
            this.ctx.textAlign = "center";
            this.ctx.fillText(username, x, y - radius - 5);

            // 血量条
            if (player.status === 'alive') {
                const barWidth = radius * 2;
                const barHeight = 4;
                this.ctx.fillStyle = "#222";
                this.ctx.fillRect(x - barWidth/2, y + radius + 5, barWidth, barHeight);
                this.ctx.fillStyle = "#ff4444";
                this.ctx.fillRect(x - barWidth/2, y + radius + 5, barWidth * (player.hp / CONFIG.MAX_HP), barHeight);
                
                // 血量数字
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#fff";
                this.ctx.fillText(player.hp, x, y + radius + 15);
            } else {
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#ff4444";
                this.ctx.fillText("DEAD", x, y + radius + 10);
            }

            // 击杀数
            if (player.kills > 0) {
                this.ctx.font = "10px Arial";
                this.ctx.fillStyle = "#ffff00";
                this.ctx.fillText(`Kills: ${player.kills}`, x, y - radius - 15);
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
                    const maxDist = CONFIG.MAX_BULLET_DIST * scaleX;
                    if (len > maxDist) {
                        dx = dx / len * maxDist;
                        dy = dy / len * maxDist;
                    }
                    
                    const tx = meX + dx;
                    const ty = meY + dy;

                    this.ctx.save();
                    this.ctx.strokeStyle = this.shootCD > 0 ? "rgba(255,0,0,0.2)" : "rgba(255,255,255,0.3)";
                    this.ctx.lineWidth = 30 * scaleX;
                    this.ctx.beginPath();
                    this.ctx.moveTo(meX, meY);
                    this.ctx.lineTo(tx, ty);
                    this.ctx.stroke();
                    this.ctx.restore();
                }
            }
        }
    }

    renderBullets(scaleX, scaleY) {
        for (const bullet of this.lastState.bullets || []) {
            const x = bullet.x * scaleX;
            const y = bullet.y * scaleY;
            const radius = CONFIG.BULLET_RADIUS * scaleX;
            
            this.ctx.beginPath();
            this.ctx.arc(x, y, radius, 0, 2 * Math.PI);
            this.ctx.fillStyle = bullet.owner === window.auth.currentUser.username ? "#ffff00" : "#ff4444";
            this.ctx.fill();
        }
    }

    renderUI(scaleX, scaleY) {
        const me = this.lastState?.players?.[window.auth.currentUser.username];
        if (!me) return;

        const meX = me.x * scaleX;
        const meY = me.y * scaleY;

        // CD显示
        if (this.shootCD > 0) {
            this.ctx.font = "16px Arial";
            this.ctx.fillStyle = "#ff4444";
            this.ctx.textAlign = "center";
            this.ctx.fillText((this.shootCD / 1000).toFixed(1), meX, meY + 5);
        }

        // 死亡复活提示
        if (me.status === 'dead') {
            this.ctx.font = "24px Arial";
            this.ctx.fillStyle = "#ff4444";
            this.ctx.textAlign = "center";
            this.ctx.fillText("你已死亡！按R键复活", this.canvas.width / 2, this.canvas.height / 2);
        }
    }

    initCDTimer() {
        setInterval(() => {
            if (this.shootCD > 0) {
                this.shootCD -= 100;
                if (this.shootCD < 0) this.shootCD = 0;
            }
        }, 100);
    }
}

window.Game = Game;