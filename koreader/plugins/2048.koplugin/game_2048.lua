local Game = {
    -- Defaults
    DEFAULT_SIZE = 4,
}

function Game:new(o)
    o = o or {}
    setmetatable(o, self)
    self.__index = self
    o.rows = o.rows or o.size or self.DEFAULT_SIZE
    o.cols = o.cols or o.size or self.DEFAULT_SIZE
    o:reset()
    return o
end

function Game:reset()
    self.board = {}
    for i = 1, self.rows do
        self.board[i] = {}
        for j = 1, self.cols do
            self.board[i][j] = 0
        end
    end
    self.score = 0
    self.over = false
    self.won = false
    self:spawn()
    self:spawn()
end

function Game:spawn()
    local empty = {}
    for i = 1, self.rows do
        for j = 1, self.cols do
            if self.board[i][j] == 0 then
                table.insert(empty, {r = i, c = j})
            end
        end
    end
    if #empty > 0 then
        local cell = empty[math.random(#empty)]
        self.board[cell.r][cell.c] = (math.random() < 0.9) and 2 or 4
    end
end

-- Generic move function using rotation
-- We normalize everything to "slide left"
function Game:move(direction)
    if self.over then return false end

    local rotated = false
    local text_dir = direction

    -- Orient board so we always slide left
    if direction == "up" then
        self:rotate(3) -- 270 deg
    elseif direction == "right" then
        self:rotate(2) -- 180 deg
    elseif direction == "down" then
        self:rotate(1) -- 90 deg
    end

    local changed = self:slide_left()

    -- Rotate back
    if direction == "up" then
        self:rotate(1)
    elseif direction == "right" then
        self:rotate(2)
    elseif direction == "down" then
        self:rotate(3)
    end

    if changed then
        self:spawn()
        if self:is_game_over() then
            self.over = true
        end
    end

    return changed
end

function Game:slide_left()
    local changed = false

    
    for i = 1, #self.board do -- Use #self.board to be safe with current dimensions
        local row = self.board[i]
        local new_row = {}
        local prev = nil
        
        -- Compress non-zeros
        local temp = {}
        for _, val in ipairs(row) do
            if val ~= 0 then table.insert(temp, val) end
        end

        local k = 1
        while k <= #temp do
            if k < #temp and temp[k] == temp[k+1] then
                table.insert(new_row, temp[k] * 2)
                self.score = self.score + temp[k] * 2
                k = k + 2
                changed = true
            else
                table.insert(new_row, temp[k])
                k = k + 1
            end
        end

        -- Check if row changed (padded with zeros)
        -- The row length should be equal to current number of columns.
        -- If we rotated, the current "logical" row length is the number of columns in this orientation.
        -- Since we modify self.board in place, #self.board[i] is the number of cols.
        local current_cols = #self.board[1]
        
        for j = 1, current_cols do
            local new_val = new_row[j] or 0
            if self.board[i][j] ~= new_val then
                changed = true
            end
            self.board[i][j] = new_val
        end
    end
    return changed
end

function Game:rotate(n)
    for _ = 1, n do
        local new_board = {}
        local current_rows = #self.board
        local current_cols = #self.board[1]
        
        for i = 1, current_cols do
            new_board[i] = {}
            for j = 1, current_rows do
                -- Rotate 90 deg clockwise: (i, j) -> (j, rows - i + 1)
                new_board[i][j] = self.board[current_rows - j + 1][i]
            end
        end
        self.board = new_board
    end
end

function Game:is_game_over()
    local rows = #self.board
    local cols = #self.board[1]

    -- Check for empty spots
    for i = 1, rows do
        for j = 1, cols do
            if self.board[i][j] == 0 then return false end
        end
    end
    -- Check for straight merges
    for i = 1, rows do
        for j = 1, cols do
            local val = self.board[i][j]
            if j < cols and val == self.board[i][j+1] then return false end
            if i < rows and val == self.board[i+1][j] then return false end
        end
    end
    return true
end


function Game:getState()
    return {
        board = self.board,
        score = self.score,
        over = self.over,
        won = self.won,
        rows = self.rows,
        cols = self.cols,
    }
end

function Game:setState(state)
    self.board = state.board
    self.end_score = state.score -- compatibility if needed, but validation is good
    self.score = state.score
    self.over = state.over
    self.won = state.won
    self.rows = state.rows
    self.cols = state.cols
end

return Game

