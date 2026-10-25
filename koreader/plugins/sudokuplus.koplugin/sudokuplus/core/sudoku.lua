local board = require("sudokuplus.core.board")
local generator = require("sudokuplus.core.generator")
local hints = require("sudokuplus.core.hints")
local solver = require("sudokuplus.core.solver")

local sudoku = {}

-- Preserve the (result, error) convention and report whether an exact search
-- exhausted the tree or stopped at the caller's requested solution limit.
-- Never return a partial result as a successful answer after budget exhaustion.
local function search_result(s, result, err, count, limit)
    if err then
        return nil, err
    end
    if s.search_capped then
        return nil, "search budget exhausted", "capped"
    end
    local status = limit and limit > 0 and count >= limit and "limit_reached" or "complete"
    return result, nil, status
end

function sudoku.from_string(s)
    return board.from_string(s)
end

function sudoku.solve_any(puzzle, opts)
    local b, err = sudoku.from_string(puzzle)
    if not b then
        return nil, err
    end
    local s, s_err = solver.new(b, opts)
    if not s then
        return nil, s_err
    end
    local result, solve_err = s:solve_any()
    return search_result(s, result, solve_err, result and 1 or 0, 1)
end

function sudoku.solve_all(puzzle, opts, limit)
    local b, err = sudoku.from_string(puzzle)
    if not b then
        return nil, err
    end
    local s, s_err = solver.new(b, opts)
    if not s then
        return nil, s_err
    end
    local result, solve_err = s:solve_all(limit)
    return search_result(s, result, solve_err, result and #result or 0, limit)
end

function sudoku.solutions_count(puzzle, opts, limit)
    local b, err = sudoku.from_string(puzzle)
    if not b then
        return nil, err
    end
    local s, s_err = solver.new(b, opts)
    if not s then
        return nil, s_err
    end
    local count, count_err = s:count_solutions(limit)
    return search_result(s, count, count_err, count, limit)
end

function sudoku.is_solved(puzzle)
    local b, err = sudoku.from_string(puzzle)
    if not b then
        return false, err
    end
    local s, solver_err = solver.new(b)
    if not s then
        return false, solver_err
    end
    return s:is_solved()
end

function sudoku.generate(opts)
    return generator.generate(opts)
end

function sudoku.generate_game(opts)
    return generator.generate_game(opts)
end

function sudoku.next_hint(state, opts)
    return hints.next(state, opts)
end

return sudoku
