local RenderText = require("ui/rendertext")
local layout = require("sudokuplus.ui.layout")

local HintOutline = {}
HintOutline.__index = HintOutline

function HintOutline.new(l, face)
    local cell = l.grid.cell
    local third = math.floor(cell / 3)
    local clearance = { left = cell, right = cell, top = cell, bottom = cell }
    -- Match paintNotes/render_centered exactly, including glyph bearings and
    -- bitmap extents. Measure all nine notes so thickness never depends on
    -- which candidates happen to remain, and never moves/shrinks note text.
    for value = 1, 9 do
        local size = RenderText:sizeUtf8Text(0, third, face, tostring(value), false, false)
        local glyph = RenderText:getGlyph(face, string.byte(tostring(value)), false)
        local x = ((value - 1) % 3) * third + math.floor((third - size.x) / 2) + glyph.l
        local y = math.floor((value - 1) / 3) * third + math.floor((third + size.y_top - size.y_bottom) / 2) - glyph.t
        clearance.left = math.min(clearance.left, x)
        clearance.right = math.min(clearance.right, cell - x - glyph.bb:getWidth())
        clearance.top = math.min(clearance.top, y)
        clearance.bottom = math.min(clearance.bottom, cell - y - glyph.bb:getHeight())
    end
    return setmetatable({ layout = l, clearance = clearance, cache = {} }, HintOutline)
end

local function stroke(target, separator, clearance)
    -- Keep a pixel of breathing room before the ink. Start centered on the
    -- cell edge, then use spare space on either side to reach the target.
    -- In tight layouts an edge can live entirely in the separator.
    local limit = math.max(0, clearance - 1)
    local inside = math.min(math.ceil(target / 2), limit)
    local outside = math.min(separator, target - inside)
    inside = math.min(limit, target - outside)
    return inside, outside
end

function HintOutline:cell(row, col)
    local key = row * 9 + col
    if self.cache[key] then
        return self.cache[key]
    end
    local l = self.layout
    local rect = layout.cell_rect(l, row, col)
    local target = 4 * l.thin
    local left, out_left = stroke(target, col % 3 == 0 and l.thick or l.thin, self.clearance.left)
    local right, out_right = stroke(target, col % 3 == 2 and l.thick or l.thin, self.clearance.right)
    local top, out_top = stroke(target, row % 3 == 0 and l.thick or l.thin, self.clearance.top)
    local bottom, out_bottom = stroke(target, row % 3 == 2 and l.thick or l.thin, self.clearance.bottom)
    local bounds = {
        x = rect.x - out_left,
        y = rect.y - out_top,
        w = rect.w + out_left + out_right,
        h = rect.h + out_top + out_bottom,
    }
    local result = {
        bounds = bounds,
        strips = {
            { x = bounds.x, y = bounds.y, w = bounds.w, h = top + out_top },
            { x = bounds.x, y = rect.y + rect.h - bottom, w = bounds.w, h = bottom + out_bottom },
            { x = bounds.x, y = bounds.y, w = left + out_left, h = bounds.h },
            { x = rect.x + rect.w - right, y = bounds.y, w = right + out_right, h = bounds.h },
        },
    }
    self.cache[key] = result
    return result
end

function HintOutline:paint(bb, row, col, ink)
    for _, strip in ipairs(self:cell(row, col).strips) do
        bb:paintRect(strip.x, strip.y, strip.w, strip.h, ink)
    end
end

return HintOutline
