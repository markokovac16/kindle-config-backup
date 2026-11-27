-- Study collections: keeps KOReader collections in sync with folders under /mnt/us/documents.
--   documents/Fax   -> "Fax"   (uni study notes)
--   documents/Maths -> "Maths" (maths prep: Savov books, A Mind for Numbers, ...)
-- Runs every boot (late, before the last book is reopened):
--   1. one-time moves listed in MOVES (file + sidecar progress + history + collections + lastfile),
--      done like the file manager's move, so reading position is kept;
--   2. for each folder: adds every EPUB/PDF in it to its collection, drops entries whose file is
--      gone or now lives in another synced folder.
-- Replaces 2-fax-once.lua (2026-11-05: renamed "Not in a collection" to "Fax"; 2026-11-27: PDFs,
-- then the Maths folder/collection and moving the two Savov books out of Fax).
local ReadCollection = require("readcollection")
local ReadHistory = require("readhistory")
local DocSettings = require("docsettings")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

local DOCS = "/mnt/us/documents"
local SYNC = {
    { dir = DOCS .. "/Fax", coll = "Fax" },
    { dir = DOCS .. "/Maths", coll = "Maths" },
}
local MOVES = {
    { "Fax", "Maths", "No Bullshit Guide to Math and Physics - Ivan Savov.epub" },
    { "Fax", "Maths", "No Bullshit Guide to Linear Algebra - Ivan Savov.epub" },
}

local function exists(p) return lfs.attributes(p, "mode") ~= nil end

local ok, err = pcall(function()
    local changed = false
    -- legacy rename from the first version of this patch
    if ReadCollection.coll["Not in a collection"] and not ReadCollection.coll["Fax"] then
        ReadCollection:renameCollection("Not in a collection", "Fax")
        changed = true
    end

    for _, m in ipairs(MOVES) do
        local old = DOCS .. "/" .. m[1] .. "/" .. m[3]
        local newdir = DOCS .. "/" .. m[2]
        local new = newdir .. "/" .. m[3]
        if exists(old) and not exists(new) then
            if not exists(newdir) then lfs.mkdir(newdir) end
            local okmv, mverr = os.rename(old, new)
            if okmv then
                DocSettings.updateLocation(old, new)   -- moves the .sdr (progress, highlights)
                ReadHistory:updateItem(old, new)
                ReadCollection:updateItem(old, new)
                if G_reader_settings:readSetting("lastfile") == old then
                    G_reader_settings:saveSetting("lastfile", new)
                end
                logger.info("study-collections: moved", old, "->", new)
                changed = true
            else
                logger.warn("study-collections: move failed", old, mverr)
            end
        end
    end

    local synced = {}
    for _, s in ipairs(SYNC) do synced[s.dir] = true end

    for _, s in ipairs(SYNC) do
        if exists(s.dir) then
            if not ReadCollection.coll[s.coll] then
                ReadCollection:addCollection(s.coll)
                changed = true
            end
            local coll = ReadCollection.coll[s.coll]
            for file in pairs(coll) do
                local parent = file:match("^(.*)/[^/]*$")
                if not exists(file) or (parent ~= s.dir and synced[parent]) then
                    coll[file] = nil
                    changed = true
                end
            end
            local names = {}
            for name in lfs.dir(s.dir) do
                if name:match("%.epub$") or name:match("%.pdf$") then table.insert(names, name) end
            end
            table.sort(names)
            for _, name in ipairs(names) do
                local path = s.dir .. "/" .. name
                if not ReadCollection:isFileInCollection(path, s.coll) then
                    ReadCollection:addItem(path, s.coll)
                    changed = true
                end
            end
        end
    end
    if changed then ReadCollection:write() end
end)
if not ok then logger.warn("study-collections:", err) end
