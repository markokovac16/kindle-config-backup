-- Full-screen DOOM: the engine (libdoom.so, doomgeneric) renders 320x200, we dither it
-- to black/white and push it with the fast A2 waveform; a touch pad below drives it.
local Blitbuffer = require("ffi/blitbuffer")
local DataStorage = require("datastorage")
local Device = require("device")
local Font = require("ui/font")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local InputContainer = require("ui/widget/container/inputcontainer")
local RenderText = require("ui/rendertext")
local UIManager = require("ui/uimanager")
local ffi = require("ffi")
local logger = require("logger")
local time = require("ui/time")
local _ = require("gettext")
local Screen = Device.screen

ffi.cdef[[
int doom_init(const char *iwad, const char *configdir);
int doom_tick(void);
void doom_key(int pressed, int key);
void doom_set_paused(int paused);
void doom_render(uint8_t *dst, int dw, int dh, int stride, int dither, int invert);
]]

-- Key codes from doomkeys.h.
local KEY = {
    right = 0xae, left = 0xac, up = 0xad, down = 0xaf,
    strafe_l = 0xa0, strafe_r = 0xa1, use = 0xa2, fire = 0xa3,
    escape = 27, enter = 13, tab = 9, rshift = 0x80 + 0x36,
    yes = string.byte("y"), next_weapon = string.byte("]"),
}

local FRAME_INTERVAL = 0.1        -- seconds between frames; the panel can't go much faster
local MIN_HOLD = time.s(0.15)     -- a quick tap still holds the key for a few tics

-- The engine can only start once per KOReader run, so its state lives in the module.
local lib
local engine_state = "idle"       -- "idle", "running" or "dead"

local DoomWidget = InputContainer:extend{
    name = "doom",
    modal = true,
    covers_fullscreen = true,
}

-- Loads and boots the engine on first use. Returns false if Doom has quit or failed.
function DoomWidget.startEngine(plugin_path)
    if engine_state == "running" then return true end
    if engine_state == "dead" then return false end
    local ok, loaded = pcall(ffi.load, plugin_path .. "/libdoom.so")
    if not ok then
        logger.err("doom: cannot load engine:", loaded)
        engine_state = "dead"
        return false
    end
    lib = loaded
    local configdir = DataStorage:getSettingsDir() .. "/doom/"
    if lib.doom_init(plugin_path .. "/doom1.wad", configdir) == 0 then
        engine_state = "dead"
        return false
    end
    engine_state = "running"
    return true
end

function DoomWidget.isDead()
    return engine_state == "dead"
end

function DoomWidget:init()
    -- A stable function, so unschedule() can find it again.
    self.step_cb = function() self:step() end
    local sw, sh = Screen:getWidth(), Screen:getHeight()
    self.dimen = Geom:new{ x = 0, y = 0, w = sw, h = sh }
    -- Doom was drawn for 4:3 screens, so stretch 320x200 back to that shape.
    self.game = Geom:new{ x = 0, y = 0, w = sw, h = math.floor(sw * 3 / 4) }
    self.bb = Blitbuffer.new(self.game.w, self.game.h, Blitbuffer.TYPE_BB8)
    self.face = Font:getFace("cfont", 22)
    self.run = false
    self:layoutButtons()

    self.ges_events = {}
    local release = { "tap", "hold_release", "pan_release", "hold_pan_release", "swipe" }
    self.ges_events.DoomTouch = { GestureRange:new{ ges = "touch", range = self.dimen } }
    for i, ges in ipairs(release) do
        self.ges_events["DoomRelease" .. i] = { GestureRange:new{ ges = ges, range = self.dimen } }
        self["onDoomRelease" .. i] = function(this, _, g) return this:onDoomRelease(g) end
    end

    lib.doom_set_paused(0)
    self.running = true
    UIManager:scheduleIn(FRAME_INTERVAL, self.step_cb)
end

function DoomWidget:layoutButtons()
    local gap = Screen:scaleBySize(6)
    local top = self.game.h + gap
    local cols, rows = 4, 4
    local cw = math.floor((self.dimen.w - gap) / cols)
    local rh = math.floor((self.dimen.h - top) / rows)
    local function cell(col, row, colspan, rowspan)
        return Geom:new{
            x = gap + col * cw, y = top + row * rh,
            w = cw * (colspan or 1) - gap, h = rh * (rowspan or 1) - gap,
        }
    end
    self.buttons = {
        { label = _("◀ Strafe"), key = KEY.strafe_l, rect = cell(0, 0) },
        { label = "▲", key = KEY.up, rect = cell(1, 0) },
        { label = _("Strafe ▶"), key = KEY.strafe_r, rect = cell(2, 0) },
        { label = _("FIRE"), key = KEY.fire, rect = cell(3, 0, 1, 2) },
        { label = "◀", key = KEY.left, rect = cell(0, 1) },
        { label = _("USE"), key = KEY.use, rect = cell(1, 1) },
        { label = "▶", key = KEY.right, rect = cell(2, 1) },
        { label = _("Map"), key = KEY.tab, rect = cell(0, 2) },
        { label = "▼", key = KEY.down, rect = cell(1, 2) },
        { label = _("Weapon"), key = KEY.next_weapon, rect = cell(2, 2) },
        { label = _("Run"), toggle = "run", rect = cell(3, 2) },
        { label = _("Menu"), key = KEY.escape, rect = cell(0, 3) },
        { label = _("Enter"), key = KEY.enter, rect = cell(1, 3) },
        { label = _("Yes"), key = KEY.yes, rect = cell(2, 3) },
        { label = _("Close"), action = "close", rect = cell(3, 3) },
    }
    -- Touching the picture itself fires too: it's the biggest target on screen.
    table.insert(self.buttons, { key = KEY.fire, rect = self.game, invisible = true })
end

function DoomWidget:buttonAt(pos)
    if not pos then return end
    for _, b in ipairs(self.buttons) do
        if b.rect:contains(pos) then return b end
    end
end

function DoomWidget:renderFrame()
    local invert = Screen.night_mode and 1 or 0
    lib.doom_render(ffi.cast("uint8_t *", self.bb.data), self.game.w, self.game.h, self.bb.stride, 1, invert)
end

function DoomWidget:paintButton(bb, b)
    local r = b.rect
    local lit = b.down or (b.toggle and self[b.toggle])
    bb:paintRect(r.x, r.y, r.w, r.h, lit and Blitbuffer.COLOR_BLACK or Blitbuffer.COLOR_WHITE)
    bb:paintBorder(r.x, r.y, r.w, r.h, Screen:scaleBySize(2), Blitbuffer.COLOR_BLACK)
    local size = RenderText:sizeUtf8Text(0, r.w, self.face, b.label, true, true)
    local baseline = r.y + math.floor((r.h - size.y_bottom - size.y_top) / 2) + size.y_top
    RenderText:renderUtf8Text(bb, r.x + math.floor((r.w - size.x) / 2), baseline, self.face, b.label,
        true, true, lit and Blitbuffer.COLOR_WHITE or Blitbuffer.COLOR_BLACK)
end

function DoomWidget:paintTo(bb, x, y)
    bb:paintRect(x, y, self.dimen.w, self.dimen.h, Blitbuffer.COLOR_WHITE)
    self:renderFrame()
    bb:blitFrom(self.bb, x + self.game.x, y + self.game.y, 0, 0, self.game.w, self.game.h)
    for _, b in ipairs(self.buttons) do
        if not b.invisible then self:paintButton(bb, b) end
    end
end

function DoomWidget:refreshButton(b)
    if b.invisible then return end
    UIManager:setDirty(self, function() return "fast", b.rect end)
end

function DoomWidget:press(b)
    if b.action == "close" then
        self:onClose()
    elseif b.toggle then
        self[b.toggle] = not self[b.toggle]
        lib.doom_key(self.run and 1 or 0, KEY.rshift)
        self:refreshButton(b)
    elseif not b.down then
        b.down = time.now()
        b.release_at = nil
        lib.doom_key(1, b.key)
        self:refreshButton(b)
    end
end

function DoomWidget:release(b)
    if b.down and not b.release_at then
        b.release_at = math.max(time.now(), b.down + MIN_HOLD)
    end
end

-- Lets go of keys whose finger has lifted, once they've been held long enough to register.
function DoomWidget:releaseDue()
    local now = time.now()
    for _, b in ipairs(self.buttons) do
        if b.release_at and now >= b.release_at then
            lib.doom_key(0, b.key)
            b.down, b.release_at = nil, nil
            self:refreshButton(b)
        end
    end
end

function DoomWidget:onDoomTouch(_, ges)
    local b = self:buttonAt(ges.pos)
    if b then self:press(b) end
    return true
end

function DoomWidget:onDoomRelease(ges)
    local b = self:buttonAt(ges.pos)
    if b and b.down then
        self:release(b)
    else
        -- The finger slid off its button: let go of everything held.
        for _, held in ipairs(self.buttons) do self:release(held) end
    end
    return true
end

function DoomWidget:step()
    if not self.running then return end
    self:releaseDue()
    if lib.doom_tick() == 0 then
        engine_state = "dead"
        self:onClose()
        return
    end
    UIManager:setDirty(self, function() return "a2", self.game end)
    UIManager:scheduleIn(FRAME_INTERVAL, self.step_cb)
end

function DoomWidget:pause()
    if not self.running then return end
    self.running = false
    UIManager:unschedule(self.step_cb)
    for _, b in ipairs(self.buttons) do
        if b.down then lib.doom_key(0, b.key) end
        b.down, b.release_at = nil, nil
    end
    if self.run then lib.doom_key(0, KEY.rshift) end
    lib.doom_set_paused(1)
end

function DoomWidget:onSuspend()
    self:pause()
end

function DoomWidget:onResume()
    if engine_state ~= "running" or self.running then return end
    lib.doom_set_paused(0)
    if self.run then lib.doom_key(1, KEY.rshift) end
    self.running = true
    UIManager:setDirty(self, "full")
    UIManager:scheduleIn(FRAME_INTERVAL, self.step_cb)
end

function DoomWidget:onClose()
    self:pause()
    UIManager:close(self, "full")
    return true
end

function DoomWidget:onCloseWidget()
    self:pause()
    if self.bb then
        self.bb:free()
        self.bb = nil
    end
    if self.on_close then self.on_close() end
end

return DoomWidget
