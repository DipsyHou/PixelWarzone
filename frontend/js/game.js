/**
 * Game — thin orchestrator wiring InputManager, WeaponManager and GameRenderer.
 *
 * Handles the control event loop (keyboard + mouse) and delegates:
 *   - weapon firing / switching  → WeaponManager
 *   - all canvas drawing         → GameRenderer
 */
class Game {

    constructor() {
        this.canvas = null;
        this.wsManager = null;
        this.lastState = null;

        this.isMouseDown = false;
        this.mousePos = null;
        this.pressedKeys = new Set();

        this.weapons = new WeaponManager();
        this.renderer = new GameRenderer();
    }

    init(canvas, wsManager) {
        this.canvas = canvas;
        this.wsManager = wsManager;
        this.weapons.initFromLoadout();
        this.renderer.init(canvas);
        this._setupControls();
    }

    // ─── input bindings ───────────────────────────

    _setupControls() {
        this.canvas.addEventListener("mousedown", (e) => this._onMouseDown(e));
        this.canvas.addEventListener("mousemove", (e) => this._onMouseMove(e));
        this.canvas.addEventListener("mouseup",   (e) => this._onMouseUp(e));
        document.addEventListener("keydown", (e) => this._onKeyDown(e));
        document.addEventListener("keyup",   (e) => this._onKeyUp(e));
    }

    _onMouseDown(e) {
        this.isMouseDown = true;
        const rect = this.canvas.getBoundingClientRect();
        this.mousePos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        this.weapons.iaidoHoldStart = this.weapons.weaponType === "iaido" ? Date.now() : undefined;
    }

    _onMouseMove(e) {
        if (this.isMouseDown) {
            const rect = this.canvas.getBoundingClientRect();
            this.mousePos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        }
    }

    _onMouseUp(e) {
        if (this.weapons.shootCD > 0 && this.weapons.weaponType !== "iaido") {
            this.isMouseDown = false;
            this.mousePos = null;
            this.render();
            return;
        }

        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const me = this.lastState?.players?.[window.auth.currentUser.username];
        if (!me || me.status !== "alive") {
            this.isMouseDown = false;
            this.mousePos = null;
            return;
        }

        this.weapons.fire(me, mx, my, this.canvas, this.wsManager, this.lastState);

        this.isMouseDown = false;
        this.mousePos = null;
        this.weapons.iaidoHoldStart = undefined;
    }

    _onKeyDown(e) {
        const key = e.key.toLowerCase();

        if (key === "r") {
            this.wsManager.respawn();
            return;
        }

        if (["w","s","a","d","arrowup","arrowdown","arrowleft","arrowright"].includes(key)) {
            this.pressedKeys.add(key);
            this._updateDirection();
                return;
            }

        if (["1","2","3","4","5","6","7"].includes(key)) {
            this.weapons.switchWeapon(key);
                return;
            }

        if (key === "x") {
            const me = this.lastState?.players?.[window.auth.currentUser.username];
            if (me && me.status === "alive") {
                this.wsManager.sendMessage({ type: "graffiti", x: me.x, y: me.y });
            }
        }
    }

    _onKeyUp(e) {
        const key = e.key.toLowerCase();
        if (["w","s","a","d","arrowup","arrowdown","arrowleft","arrowright"].includes(key)) {
            this.pressedKeys.delete(key);
            this._updateDirection();
        }
    }

    _updateDirection() {
        let dx = 0, dy = 0;
        if (this.pressedKeys.has("w") || this.pressedKeys.has("arrowup"))    dy -= CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("s") || this.pressedKeys.has("arrowdown"))  dy += CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("a") || this.pressedKeys.has("arrowleft"))  dx -= CONFIG.PLAYER_SPEED;
        if (this.pressedKeys.has("d") || this.pressedKeys.has("arrowright")) dx += CONFIG.PLAYER_SPEED;
        if (dx !== 0 && dy !== 0) { dx /= Math.sqrt(2); dy /= Math.sqrt(2); }
        this.wsManager.move(dx, dy);
    }

    // ─── state / render ───────────────────────────

    updateState(state) {
        if (!state || !state.players) {
            if (state?.message) window.ui?.showTip?.(state.message);
            return;
        }
        this.lastState = state;
        const me = state.players[window.auth?.currentUser?.username];
        this.weapons.syncFromPlayer(me);
        this.render();
        if (state.room_info) {
            window.ui.updateRoomInfo(state.room_info);
        }
    }

    render() {
        this.renderer.render(this.lastState, this.weapons, this.isMouseDown, this.mousePos);
    }
}

window.Game = Game;
