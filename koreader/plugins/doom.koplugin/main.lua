local Dispatcher = require("dispatcher")
local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local _ = require("gettext")

local DoomWidget = require("doomwidget")

local Doom = WidgetContainer:extend{
    name = "doom",
    is_doc_only = false,
}

function Doom:init()
    Dispatcher:registerAction("doom_start", { category = "none", event = "StartDoom", title = _("Play DOOM"), general = true })
    self.ui.menu:registerToMainMenu(self)
end

function Doom:addToMainMenu(menu_items)
    menu_items.doom = {
        text = _("DOOM"),
        sorting_hint = "more_tools",
        callback = function() self:startGame() end,
    }
end

function Doom:onStartDoom()
    self:startGame()
end

local function showQuitMessage()
    UIManager:show(InfoMessage:new{ text = _("DOOM has quit. Restart KOReader to play again.") })
end

function Doom:startGame()
    if DoomWidget.isDead() then
        showQuitMessage()
        return
    end
    -- First start loads the WAD, which blocks for a moment; say so before it does.
    local loading = InfoMessage:new{ text = _("Loading DOOM…") }
    UIManager:show(loading)
    UIManager:forceRePaint()
    UIManager:nextTick(function()
        local ok = DoomWidget.startEngine(self.path)
        UIManager:close(loading)
        if not ok then
            showQuitMessage()
            return
        end
        UIManager:show(DoomWidget:new{
            on_close = function()
                if DoomWidget.isDead() then showQuitMessage() end
            end,
        }, "full")
    end)
end

return Doom
