-- Clean titles/authors for books whose built-in metadata is messy. Written as KOReader custom
-- metadata (<book>.sdr/custom_metadata.lua, same as Book information → edit), so it survives
-- cache rebuilds and can be reset from that menu. The books' cover-cache rows are dropped so
-- the home screen re-reads them. Applied once per FIXES_VERSION.
local DataStorage = require("datastorage")
local LuaSettings = require("luasettings")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

local FIXES_VERSION = 1
local D = "/mnt/us/documents/"
local FIXES = {
    ["(Texts in Computer Science) Steven S. Skiena - The Algorithm Design Manual-Springer (2020).mobi"] = { title = "The Algorithm Design Manual", authors = "Steven S. Skiena" },
    ["Dance with Dragons_ A Song of Ice and Fire_ Book Five, A - George R. R. Martin.mobi"] = { title = "A Dance with Dragons" },
    ["Feast For Crows, A - George R. R. Martin.mobi"] = { title = "A Feast for Crows" },
    ["Game Of Thrones, A - George R. R. Martin.mobi"] = { title = "A Game of Thrones" },
    ["Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones - James Clear.mobi"] = { title = "Atomic Habits" },
    ["Eloquent-JavaScript - Marijn Haverbeke.azw"] = { title = "Eloquent JavaScript" },
    ["Head First Software Architecture - Mark Richards Raju Gandhi & Neal Ford.mobi"] = { authors = "Raju Gandhi\nMark Richards\nNeal Ford" },
    ["Mastering API Architecture - Daniel Bryant James Gough & Matthew Auburn.mobi"] = { authors = "James Gough\nDaniel Bryant\nMatthew Auburn" },
    ["Structure and Interpretation of Computer Programs - Abelson & Sussman.mobi"] = { title = "Structure and Interpretation of Computer Programs", authors = "Harold Abelson\nGerald Jay Sussman" },
    ["Hobbit_ or, there and back again, The - J. R. R. Tolkien.mobi"] = { title = "The Hobbit" },
    ["Lord of the Rings, The - J.R.R.Tolkien.mobi"] = { authors = "J. R. R. Tolkien" },
    ["Pragmatic Programmer (Ephriam J Daniels' Library), The - Andy Hunt Dave Thomas.mobi"] = { title = "The Pragmatic Programmer", authors = "Andy Hunt\nDave Thomas" },
    ["You Don't Know JS_ Up & Going - Kyle Simpson.mobi"] = { title = "You Don't Know JS: Up & Going" },
}
for n = 1, 6 do
    FIXES["History of the Decline and Fall of the Roman Empire - Volume " .. n .. " - Edward Gibbon.mobi"] =
        { title = "The Decline and Fall of the Roman Empire, Vol. " .. n }
end

if (G_reader_settings:readSetting("titles_fixes_version") or 0) < FIXES_VERSION then
    -- Books sit in Calibre's "Author/" folders; find each by name.
    local found = {}
    local function walk(dir)
        for f in lfs.dir(dir) do
            if f ~= "." and f ~= ".." and f:sub(1, 1) ~= "." then
                local path = dir .. "/" .. f
                local mode = lfs.attributes(path, "mode")
                if mode == "directory" and not f:find("%.sdr$") then
                    walk(path)
                elseif mode == "file" and FIXES[f] then
                    found[f] = path
                end
            end
        end
    end
    pcall(walk, D:sub(1, -2))

    local fixed, dropped = 0, 0
    local cache = DataStorage:getSettingsDir() .. "/PT_bookinfo_cache.sqlite3"
    local ok_db, db = pcall(function() return require("lua-ljsqlite3/init").open(cache) end)
    for name, path in pairs(found) do
        local fix = FIXES[name]
        local sdr = path:gsub("%.[^.]+$", "") .. ".sdr"
        if lfs.attributes(sdr, "mode") ~= "directory" then lfs.mkdir(sdr) end
        local s = LuaSettings:open(sdr .. "/custom_metadata.lua")
        local props = s:readSetting("custom_props") or {}
        for k, v in pairs(fix) do props[k] = v end
        s:saveSetting("custom_props", props)
        local dir, file = path:match("^(.*/)([^/]+)$")
        if not s:has("doc_props") then
            -- Copy of the original metadata, which KOReader restores when a custom value is reset.
            local orig = {}
            if ok_db then
                local stmt = db:prepare("SELECT title, authors FROM bookinfo WHERE directory = ? AND filename = ?")
                local row = stmt:reset():bind(dir, file):step()
                if row then orig.title, orig.authors = row[1] and tostring(row[1]), row[2] and tostring(row[2]) end
                stmt:close()
            end
            s:saveSetting("doc_props", orig)
        end
        s:flush()
        fixed = fixed + 1
        if ok_db then
            db:prepare("DELETE FROM bookinfo WHERE directory = ? AND filename = ?"):reset():bind(dir, file):step()
            dropped = dropped + 1
        end
    end
    if ok_db then db:close() end
    logger.info("titles: custom metadata for", fixed, "books, cache rows dropped:", dropped, ok_db and "" or db)
    G_reader_settings:saveSetting("titles_fixes_version", FIXES_VERSION)
end
