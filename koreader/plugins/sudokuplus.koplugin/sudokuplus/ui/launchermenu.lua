local Menu = require("ui/widget/menu")
local Screen = require("device").screen

-- Reuse the Tools submenu's entries in a standalone, shortcut-friendly Menu.
local LauncherMenu = Menu:extend {
    name = "sudokuplus_launcher",
}

function LauncherMenu:init()
    self.width = Screen:getWidth()
    Menu.init(self)
end

function LauncherMenu:updateItems(...)
    for _, item in ipairs(self.item_table) do
        if item.enabled_func then
            item.dim = not item.enabled_func()
        end
        if item.checked_func then
            item.mandatory_func = function()
                return item.checked_func() and "✓" or ""
            end
        end
    end
    return Menu.updateItems(self, ...)
end

function LauncherMenu:onMenuSelect(item)
    if item.enabled_func and not item.enabled_func() then
        return true
    end
    if item.sub_item_table then
        return Menu.onMenuSelect(self, item)
    end
    -- Close even a nested difficulty menu before starting/resuming a game.
    -- Statistics and Help return here; a settings toggle also stays open.
    if not item.keep_menu_open and not item.checked_func then
        self:onCloseAllMenus()
    end
    if item.callback then
        item.callback()
    end
    if item.checked_func then
        self:updateItems()
    end
    return true
end

return LauncherMenu
