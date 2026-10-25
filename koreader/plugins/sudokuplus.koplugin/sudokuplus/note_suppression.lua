local bit = require("bit")
local masks = require("sudokuplus.core.masks")
local util = require("sudokuplus.core.util")

local suppression = {}

-- A suppressed bit belongs to the noted cell, not to the first placement
-- that hid it. It survives until all blockers disappear or the user removes it.
function suppression.restore_available(self)
    local restored = {}
    local constraints = util.constraint_masks_for(self.board)
    for r = 0, 8 do
        for c = 0, 8 do
            if self.board[util.cell_index(r, c)] == 0 then
                local pending = self.auto_removed[r + 1][c + 1]
                local legal = masks.compute_candidates_mask_for_cell(constraints, r, c)
                local available = bit.band(pending, legal)
                self.auto_removed[r + 1][c + 1] = bit.band(pending, bit.bnot(available))
                local add =
                    bit.band(available, bit.bnot(self.manual_removed[r + 1][c + 1]), bit.bnot(self.notes[r + 1][c + 1]))
                self.notes[r + 1][c + 1] = bit.bor(self.notes[r + 1][c + 1], add)
                for value = 1, 9 do
                    if bit.band(add, bit.lshift(1, value - 1)) ~= 0 then
                        restored[#restored + 1] = { r, c, value }
                    end
                end
            end
        end
    end
    return restored
end

-- Store only changed cells in history rather than two full grids per move.
function suppression.diff(before, after)
    local changes = {}
    for r = 1, 9 do
        for c = 1, 9 do
            if before[r][c] ~= after[r][c] then
                changes[#changes + 1] = { r = r - 1, c = c - 1, old = before[r][c], new = after[r][c] }
            end
        end
    end
    return changes
end

-- Legacy saves recorded effects on placements/erasures. Reconstruct the
-- outstanding suppression from the applied prefix, including a first blocker
-- already erased while another blocker still hid its notes.
function suppression.from_history(history, undo_ptr, notes)
    local grid = util.new_mask_grid()
    for i = 1, undo_ptr do
        local entry = history[i]
        if entry.suppression then
            for _, change in ipairs(entry.suppression) do
                grid[change.r + 1][change.c + 1] = change.new
            end
        else
            for _, cell in ipairs(entry.restored or {}) do
                grid[cell[1] + 1][cell[2] + 1] =
                    bit.band(grid[cell[1] + 1][cell[2] + 1], bit.bnot(bit.lshift(1, cell[3] - 1)))
            end
            for _, cell in ipairs(entry.cleaned or {}) do
                grid[cell[1] + 1][cell[2] + 1] = bit.bor(grid[cell[1] + 1][cell[2] + 1], bit.lshift(1, cell[3] - 1))
            end
        end
    end
    for r = 1, 9 do
        for c = 1, 9 do
            grid[r][c] = bit.band(grid[r][c], bit.bnot(notes[r][c]))
        end
    end
    return grid
end

function suppression.apply_history(self, entry, forward)
    if entry.suppression then
        for _, change in ipairs(entry.suppression) do
            self.auto_removed[change.r + 1][change.c + 1] = forward and change.new or change.old
        end
    elseif entry.kind == "place" or entry.kind == "erase" then
        local ptr = self.undo_ptr + (forward and 1 or -1)
        self.auto_removed = suppression.from_history(self.history, ptr, self.notes)
    end
end

return suppression
