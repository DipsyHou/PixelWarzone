const BACKEND_URL = "47.86.22.26:3000";
const MAP_WIDTH = 1920;
const MAP_HEIGHT = 1080;
const MAX_BULLET_DIST = 800; // 子弹最大距离

let ws = null;
let myName = "player" + Math.floor(Math.random() * 10000);
let myDir = {dx: 0, dy: 0};

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

let lastState = null;
let shootCD = 0; // 单位：毫秒

let isMouseDown = false;
let mousePos = null;

// 鼠标按下，开始显示轨迹
canvas.addEventListener("mousedown", function(e) {
    isMouseDown = true;
    const rect = canvas.getBoundingClientRect();
    mousePos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
});

// 鼠标移动，实时更新轨迹终点
canvas.addEventListener("mousemove", function(e) {
    if (isMouseDown) {
        const rect = canvas.getBoundingClientRect();
        mousePos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
});

// 鼠标松开，发射子弹并清除轨迹
canvas.addEventListener("mouseup", function(e) {
    if (shootCD > 0) {
        isMouseDown = false;
        mousePos = null;
        return;
    }

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const me = lastState?.players?.[myName];
    if (!me) {
        isMouseDown = false;
        mousePos = null;
        return;
    }

    let dx = mouseX - me.x;
    let dy = mouseY - me.y;
    let len = Math.sqrt(dx*dx + dy*dy);
    if (len === 0) {
        isMouseDown = false;
        mousePos = null;
        return;
    }
    // 限制发射方向长度
    if (len > MAX_BULLET_DIST) {
        dx = dx / len * MAX_BULLET_DIST;
        dy = dy / len * MAX_BULLET_DIST;
        len = MAX_BULLET_DIST;
    }
    // 速度归一化
    dx = dx / len * 20;
    dy = dy / len * 20;

    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: "shoot", dx, dy, max_dist: MAX_BULLET_DIST}));
        shootCD = 1000; // 1秒CD
    }
    isMouseDown = false;
    mousePos = null;
});

function connectWebSocket() {
    ws = new WebSocket(`ws://${BACKEND_URL}/ws/${myName}`);
    ws.onopen = () => {
        console.log("WebSocket连接成功，用户名：", myName);
    };
    ws.onmessage = (event) => {
        const state = JSON.parse(event.data);
        lastState = state;
        render2D(state);
    };
    ws.onerror = (e) => {
        console.error("WebSocket连接错误", e);
    };
    ws.onclose = () => {
        alert("WebSocket 断开，请刷新页面重连");
    };
}

function render2D(state) {
    ctx.clearRect(0, 0, MAP_WIDTH, MAP_HEIGHT);

    // 地图边界
    ctx.strokeStyle = "#ff0000";
    ctx.lineWidth = 4;
    ctx.strokeRect(0, 0, MAP_WIDTH, MAP_HEIGHT);

    // 所有玩家
    for (const [username, player] of Object.entries(state.players)) {
        ctx.beginPath();
        ctx.arc(player.x, player.y, 30, 0, 2 * Math.PI);
        ctx.fillStyle = username === myName ? "#00ff00" : "#0000ff";
        ctx.fill();
        ctx.strokeStyle = "#222";
        ctx.stroke();

        // 玩家名
        ctx.font = "20px Arial";
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.fillText(username, player.x, player.y - 40);

        // 血量条
        ctx.fillStyle = "#222";
        ctx.fillRect(player.x - 30, player.y + 35, 60, 8);
        ctx.fillStyle = "#ff4444";
        ctx.fillRect(player.x - 30, player.y + 35, 60 * (player.hp / 1000), 8);

        // 血量数字（居中显示在血条内部）
        ctx.font = "14px Arial";
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(player.hp, player.x, player.y + 39);

        // 如果是自己，显示CD数字
        if (username === myName && shootCD > 0) {
            ctx.font = "32px Arial";
            ctx.fillStyle = "#ff4444";
            ctx.textAlign = "center";
            ctx.fillText((shootCD / 1000).toFixed(1), player.x, player.y + 10);
        }
    }

    // 发射轨迹（长度限制）
    if (isMouseDown && mousePos) {
        const me = state.players?.[myName];
        if (me) {
            let dx = mousePos.x - me.x;
            let dy = mousePos.y - me.y;
            let len = Math.sqrt(dx*dx + dy*dy);
            // 始终用最大距离
            if (len === 0) return;
            dx = dx / len * MAX_BULLET_DIST;
            dy = dy / len * MAX_BULLET_DIST;
            let tx = me.x + dx;
            let ty = me.y + dy;

            ctx.save();
            ctx.strokeStyle = shootCD > 0 ? "rgba(255,0,0,0.2)" : "rgba(255,255,255,0.3)";
            ctx.lineWidth = 30; // 与判定宽度一致
            ctx.beginPath();
            ctx.moveTo(me.x, me.y);
            ctx.lineTo(tx, ty);
            ctx.stroke();
            ctx.restore();
        }
    }
// ..

    // 所有子弹
    for (const bullet of state.bullets || []) {
        ctx.beginPath();
        ctx.arc(bullet.x, bullet.y, 10, 0, 2 * Math.PI);
        ctx.fillStyle = bullet.owner === myName ? "#ffff00" : "#ff4444";
        ctx.fill();
    }
}

// 控制逻辑
const pressedKeys = new Set();

function updateDirection() {
    let dx = 0, dy = 0;
    if (pressedKeys.has("w") || pressedKeys.has("ArrowUp")) dy -= 6;
    if (pressedKeys.has("s") || pressedKeys.has("ArrowDown")) dy += 6;
    if (pressedKeys.has("a") || pressedKeys.has("ArrowLeft")) dx -= 6;
    if (pressedKeys.has("d") || pressedKeys.has("ArrowRight")) dx += 6;
    // 斜向归一化
    if (dx !== 0 && dy !== 0) {
        const norm = Math.sqrt(2);
        dx /= norm;
        dy /= norm;
    }
    myDir = {dx, dy};
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: "move", dx, dy}));
    }
}

document.addEventListener("keydown", (e) => {
    if (
        e.key === "w" || e.key === "ArrowUp" ||
        e.key === "s" || e.key === "ArrowDown" ||
        e.key === "a" || e.key === "ArrowLeft" ||
        e.key === "d" || e.key === "ArrowRight"
    ) {
        pressedKeys.add(e.key);
        updateDirection();
    }
});

document.addEventListener("keyup", (e) => {
    if (
        e.key === "w" || e.key === "ArrowUp" ||
        e.key === "s" || e.key === "ArrowDown" ||
        e.key === "a" || e.key === "ArrowLeft" ||
        e.key === "d" || e.key === "ArrowRight"
    ) {
        pressedKeys.delete(e.key);
        updateDirection();
    }
});

// CD计时器
setInterval(() => {
    if (shootCD > 0) {
        shootCD -= 100;
        if (shootCD < 0) shootCD = 0;
    }
}, 100);

// 初始化
window.onload = function() {
    connectWebSocket();
};
