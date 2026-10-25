local WidgetContainer = require("ui/widget/container/widgetcontainer")
local Dispatcher = require("dispatcher")
local UIManager = require("ui/uimanager")
local _ = require("gettext")

local Game2048Widget = require("2048_widget")

local Game2048 = WidgetContainer:extend{
    name = "2048",
    is_doc_only = false,
}

function Game2048:init()
    self:onDispatcherRegisterActions()
    self.ui.menu:registerToMainMenu(self)
end

function Game2048:onDispatcherRegisterActions()
    Dispatcher:registerAction("start_game_2048", {category="none", event="StartGame2048", title=_("Start 2048"), general=true,})
end

function Game2048:onStartGame2048()
    self:startGame()
end

function Game2048:addToMainMenu(menu_items)
    menu_items.game_2048 = {
        text = _("2048"),
        sorting_hint = "tools",
        callback = function()
            self:startGame()
        end,
    }
end

function Game2048:startGame()
    local game_ui = Game2048Widget:new{
        name = "game_2048",
    }
    UIManager:show(game_ui)
end

return Game2048
