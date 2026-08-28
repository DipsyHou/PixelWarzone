/**
 * Client bootstrap config.
 * Combat / map numbers come from GET /api/game-config.
 *
 * API / WebSocket default to the same host that served this page
 * (works for localhost, LAN IP, and domain alike).
 */
const CONFIG = {
    // Optional override, e.g. "pixel.houxh.com" or "192.168.1.5:3000".
    // Leave empty to use window.location.host (recommended).
    BACKEND_URL: "",
    COPYRIGHT_NAME: "DipsyHou",
    COPYRIGHT_YEAR: "2025",

    MAP_WIDTH: 1920,
    MAP_HEIGHT: 1080,
    PLAYER_SPEED: 4,
    MAX_HP: 1000,
    PLAYER_RADIUS: 30,
};

function backendHost() {
    if (CONFIG.BACKEND_URL) return CONFIG.BACKEND_URL;
    return window.location.host;
}

function apiUrl(path) {
    const p = path.startsWith("/") ? path : `/${path}`;
    // Same-origin relative URL when no override — avoids mixed-content / wrong-host issues.
    if (!CONFIG.BACKEND_URL) return p;
    const proto = window.location.protocol === "https:" ? "https:" : "http:";
    return `${proto}//${CONFIG.BACKEND_URL}${p}`;
}

function wsUrl(path) {
    const p = path.startsWith("/") ? path : `/${path}`;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${backendHost()}${p}`;
}

async function loadGameConfig() {
    try {
        const res = await fetch(apiUrl("/api/game-config"));
        const data = await res.json();
        if (data && data.success && data.config) {
            Object.assign(CONFIG, data.config);
            window.CONFIG = CONFIG;
            return true;
        }
    } catch (e) {
        console.warn("Failed to load game-config from server, using defaults", e);
    }
    return false;
}

window.CONFIG = CONFIG;
window.apiUrl = apiUrl;
window.wsUrl = wsUrl;
window.loadGameConfig = loadGameConfig;
