-- Comics / manga (CBZ etc.): a full refresh every 2 pages while one is open, so dark areas
-- don't ghost into the next page. Books keep their no-flash page turns.
-- Right-to-left reading + dithering for /mnt/us/documents/Manga come from settings/directory_defaults.lua.
local ReaderUI = require("apps/reader/readerui")
local UIManager = require("ui/uimanager")
local util = require("util")

local COMIC = { cbz = true, cbr = true, cb7 = true, cbt = true }
local COMIC_REFRESH = 2
local comic_open = false

local function isComic(file)
    return file and COMIC[util.getFileNameSuffix(file):lower()] or false
end

local orig_init = ReaderUI.init
function ReaderUI:init(...)
    orig_init(self, ...)
    comic_open = self.document ~= nil and isComic(self.document.file)
    if comic_open then
        UIManager.FULL_REFRESH_COUNT = COMIC_REFRESH
        UIManager.refresh_count = 0
    end
end

local orig_close = ReaderUI.onClose
function ReaderUI:onClose(...)
    if comic_open then
        comic_open = false
        UIManager:ToggleNightMode(G_reader_settings:isTrue("night_mode")) -- back to the book rate
    end
    return orig_close(self, ...)
end

-- Night mode switching (e.g. auto warmth at dusk) resets the rate; keep the comic one.
local orig_night = UIManager.ToggleNightMode
function UIManager:ToggleNightMode(...)
    orig_night(self, ...)
    if comic_open then self.FULL_REFRESH_COUNT = COMIC_REFRESH end
end

-- Series collections are made by the home plugin (one per Manga/ subfolder); the umbrella
-- "Manga" collection an earlier version of this patch created goes away (once).
if not G_reader_settings:isTrue("manga_collection_removed") then
    local ReadCollection = require("readcollection")
    ReadCollection:_read()
    if ReadCollection.coll["Manga"] then
        ReadCollection:removeCollection("Manga")
        ReadCollection:write()
    end
    G_reader_settings:makeTrue("manga_collection_removed")
end
