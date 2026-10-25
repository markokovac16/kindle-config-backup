local Blitbuffer = require("ffi/blitbuffer")
local ButtonTable = require("ui/widget/buttontable")
local Device = require("device")
local Font = require("ui/font")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local InputContainer = require("ui/widget/container/inputcontainer")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local VerticalGroup = require("ui/widget/verticalgroup")
local FrameContainer = require("ui/widget/container/framecontainer")
local CenterContainer = require("ui/widget/container/centercontainer")
local TextWidget = require("ui/widget/textwidget")
local UIManager = require("ui/uimanager")
local TitleBar = require("ui/widget/titlebar")
local InfoMessage = require("ui/widget/infomessage")
local _ = require("gettext")

local Game = require("game_2048")

local Game2048Widget = InputContainer:extend{
    name = "game_2048_widget",
    modal = true,
    covers_fullscreen = true,
}

local LuaSettings = require("luasettings")
local DataStorage = require("datastorage")

function Game2048Widget:init()
    self.dimen = Device.screen:getSize()
    self.screen_width = self.dimen.w
    self.screen_height = self.dimen.h
    self.width = self.dimen.w
    self.height = self.dimen.h
    
    self.settings = LuaSettings:open(DataStorage:getSettingsDir() .. "/2048_settings.lua")
    self.grid_size = self.settings:readSetting("grid_size") or 4
    self:loadHighScore()
    
    self.game = Game:new{ size = self.grid_size }

    self.title_font = Font:getFace("cfont", 36)
    self.score_font = Font:getFace("cfont", 24)
    self.tile_font_large = Font:getFace("cfont", 40)
    self.tile_font_small = Font:getFace("cfont", 24)

    self.margin = 10
    
    
    self.ges_events = {
        Swipe = {
            GestureRange:new{
                ges = "swipe",
                range = self.dimen,
            }
        },
        Tap = {
            GestureRange:new{
                ges = "tap",
                range = self.dimen,
            }
        },
    }

    self.key_events = {
        ExitGame = { { "Back" }, doc = "close game" },
    }



    self:buildUI()
end

-- Layout is now calculated dynamically in buildUI
-- function Game2048Widget:calculateLayout()
-- end

function Game2048Widget:buildUI()
    -- 1. Create Control Widgets first to measure them
    local title_bar = TitleBar:new{
        title = "",
        title = "",
        subtitle = "Score: " .. self.game.score .. "   Best: " .. self.high_score,
        close_callback = function() self:onExitGame() end,
    }

    local dpad = ButtonTable:new{
        width = self.screen_width,
        buttons = {
            {
                {
                    text = "↑",
                    callback = function() self:doMove("up") end,
                },
            },
            {
                {
                    text = "←",
                    callback = function() self:doMove("left") end,
                },
                {
                    text = "↓",
                    callback = function() self:doMove("down") end,
                },
                {
                    text = "→",
                    callback = function() self:doMove("right") end,
                },
            }
        }
    }

    local control_bar = ButtonTable:new{
        width = self.screen_width,
        buttons = {
            {
                {
                    text = _("New"),
                    callback = function() 
                        self.game:reset()
                        self:checkHighScore() -- just in case, though score resets to 0
                        self:refreshUI()
                    end,
                },
                {
                    text = string.format("%dx%d", self.grid_size, self.grid_size),
                    callback = function() self:cycleGridSize() end,
                },
                {
                    text = _("Save"),
                    callback = function() self:saveGame() end,
                },
                {
                    text = _("Load"),
                    callback = function() self:loadGame() end,
                },
            }
        }
    }

    -- 2. Calculate Layout
    local title_h = title_bar:getHeight()
    local dpad_h = dpad:getSize().h
    local control_h = control_bar:getSize().h
    
    -- Remaining space for the board
    local available_h = self.screen_height - (title_h + dpad_h + control_h)
    local available_w = self.screen_width
    
    -- Add some margin safety
    -- Use scaled margin to account for high DPI/bezels
    -- Increasing to 120 pixels (unscaled) or scaled equivalent to ensure buttons fit
    -- VerticalGroup might implicitly add some spacing, so we need to be generous.
    local safety_margin = Device.screen:scaleBySize(50)
    available_h = available_h - safety_margin
    available_w = available_w - 20 -- 10px each side
    
    self.board_size = math.min(available_h, available_w)
    -- Recalculate tile size based on new board size
    self.tile_size = math.floor((self.board_size - (self.margin * (self.grid_size + 1))) / self.grid_size)

    -- 3. Create Board
    local game_board = WidgetContainer:new{
        dimen = Geom:new{ w = self.board_size, h = self.board_size },
    }
    game_board.paintTo = function(widget, bb, x, y)
        self:drawBoard(bb, x, y)
    end

    -- 4. Assemble UI
    self[1] = FrameContainer:new{
        width = self.screen_width,
        height = self.screen_height,
        background = Blitbuffer.COLOR_WHITE,
        padding = 0,
        bordersize = 0,
        VerticalGroup:new{
            align = "center",
            title_bar,
            control_bar,
            game_board,
            dpad,
        }
    }
end

function Game2048Widget:drawBoard(bb, x, y)
    -- Background
    bb:paintRect(x, y, self.board_size, self.board_size, Blitbuffer.COLOR_BLACK)
    
    for r = 1, self.grid_size do
        for c = 1, self.grid_size do
            local val = self.game.board[r][c]
            local tx = x + self.margin + (c-1)*(self.tile_size + self.margin)
            local ty = y + self.margin + (r-1)*(self.tile_size + self.margin)
            
            -- Draw tile background
            local color = val == 0 and Blitbuffer.COLOR_WHITE or Blitbuffer.COLOR_LIGHT_GRAY
            bb:paintRect(tx, ty, self.tile_size, self.tile_size, color)
            
            if val > 0 then
                bb:paintBorder(tx, ty, self.tile_size, self.tile_size, 2, Blitbuffer.COLOR_BLACK)
                -- Draw number
                local s_val = tostring(val)
                local font = (#s_val > 3) and self.tile_font_small or self.tile_font_large
                local text = TextWidget:new{
                    text = s_val,
                    face = font,
                    fgcolor = Blitbuffer.COLOR_BLACK,
                }
                
                -- Center text
                local tw = text:getSize().w
                local th = text:getSize().h
                local dx = tx + (self.tile_size - tw) / 2
                local dy = ty + (self.tile_size - th) / 2
                text:paintTo(bb, dx, dy)
                text:free()
            end
        end
    end
    
    if self.game.over then
        -- Draw Game Over overlay?
        -- Just simple text for now
        local text = TextWidget:new{
            text = "Game Over!",
            face = self.title_font,
            fgcolor = Blitbuffer.COLOR_BLACK
        }
        local tw = text:getSize().w
        local th = text:getSize().h
        bb:paintRect(x + (self.board_size - tw)/2 - 10, y + (self.board_size - th)/2 - 10, tw + 20, th + 20, Blitbuffer.COLOR_WHITE)
        bb:paintBorder(x + (self.board_size - tw)/2 - 10, y + (self.board_size - th)/2 - 10, tw + 20, th + 20, 2, Blitbuffer.COLOR_BLACK)
        text:paintTo(bb, x + (self.board_size - tw)/2, y + (self.board_size - th)/2)
        text:free()
    end
end

function Game2048Widget:doMove(dir)
    if self.game:move(dir) then
        self:checkHighScore()
        self:refreshUI()
    end
end

function Game2048Widget:onSwipe(arg, ges)
    if ges.direction == "north" then self:doMove("up")
    elseif ges.direction == "south" then self:doMove("down")
    elseif ges.direction == "east" then self:doMove("right")
    elseif ges.direction == "west" then self:doMove("left")
    end
    return true
end

function Game2048Widget:refreshUI()
    self[1] = nil -- clear old UI
    self:buildUI() -- rebuild
    UIManager:setDirty(self, "partial")
end

function Game2048Widget:cycleGridSize()
    self.grid_size = self.grid_size + 1
    if self.grid_size > 8 then
        self.grid_size = 3
    end
    
    self.settings:saveSetting("grid_size", self.grid_size)
    self.settings:flush()
    
    self.game = Game:new{ size = self.grid_size }
    self:loadHighScore()
    -- self:calculateLayout() -- Layout done in refreshUI->buildUI
    self:refreshUI()
end

function Game2048Widget:loadHighScore()
    self.high_score = self.settings:readSetting("high_score_" .. self.grid_size) or 0
end

function Game2048Widget:checkHighScore()
    if self.game.score > self.high_score then
        self.high_score = self.game.score
        self.settings:saveSetting("high_score_" .. self.grid_size, self.high_score)
        self.settings:flush()
    end
end


function Game2048Widget:saveGame()
    local state = self.game:getState()
    self.settings:saveSetting("saved_game_" .. self.grid_size, state)
    self.settings:flush()
    UIManager:show(InfoMessage:new{text = string.format(_("Game saved (%dx%d)"), self.grid_size, self.grid_size)})
end

function Game2048Widget:loadGame()
    local state = self.settings:readSetting("saved_game_" .. self.grid_size)
    if not state then
        UIManager:show(InfoMessage:new{text = string.format(_("No saved game found for %dx%d"), self.grid_size, self.grid_size)})
        return
    end

    -- We are loading a game into the current grid size, so no need to change self.grid_size
    -- But we should verify state.rows matches self.grid_size just in case of corruption
    if state.rows ~= self.grid_size then
        UIManager:show(InfoMessage:new{text = _("Save file mismatch")})
        return
    end

    self.game = Game:new{ size = self.grid_size }
    self.game:setState(state)
    
    -- Update high score reference for the loaded size (should be same)
    self:loadHighScore()
    
    self:refreshUI()
    UIManager:show(InfoMessage:new{text = string.format(_("Game loaded (%dx%d)"), self.grid_size, self.grid_size)})
end

function Game2048Widget:onExitGame()
    UIManager:tickAfterNext(function()
        UIManager:close(self)
    end)
    return true
end

return Game2048Widget
