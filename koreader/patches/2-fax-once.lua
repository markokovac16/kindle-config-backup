-- Keeps the "Fax" collection in sync with /mnt/us/documents/Fax (study notes and textbooks).
-- Runs every boot: adds any EPUB/PDF in that folder, drops entries whose file is gone. Created
-- 2026-11-05 (also renamed "Not in a collection" to "Fax"); PDFs added 2026-11-27.
local ReadCollection = require("readcollection")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

local OLD, NEW, DIR = "Not in a collection", "Fax", "/mnt/us/documents/Fax"

local ok, err = pcall(function()
    local changed = false
    if ReadCollection.coll[OLD] and not ReadCollection.coll[NEW] then
        ReadCollection:renameCollection(OLD, NEW)
        changed = true
    end
    if not ReadCollection.coll[NEW] then
        ReadCollection:addCollection(NEW)
        changed = true
    end
    local coll = ReadCollection.coll[NEW]
    -- drop entries whose file is gone (the old mobis)
    for file in pairs(coll) do
        if not lfs.attributes(file, "mode") then
            coll[file] = nil
            changed = true
        end
    end
    local names = {}
    for name in lfs.dir(DIR) do
        if name:match("%.epub$") or name:match("%.pdf$") then table.insert(names, name) end
    end
    table.sort(names)
    for _, name in ipairs(names) do
        local path = DIR .. "/" .. name
        if not ReadCollection:isFileInCollection(path, NEW) then
            ReadCollection:addItem(path, NEW)
            changed = true
        end
    end
    if changed then ReadCollection:write() end
end)
if not ok then logger.warn("fax-once:", err) end
