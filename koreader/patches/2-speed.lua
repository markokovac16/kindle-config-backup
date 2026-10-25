-- Snappier KOReader (applied once): fewer UI flashes, skip plugins that aren't used.
if not G_reader_settings:isTrue("speed_tweaks_applied") then
    G_reader_settings:makeTrue("avoid_flashing_ui")
    local disabled = G_reader_settings:readSetting("plugins_disabled") or {}
    for _, name in ipairs{
        "archiveviewer", "autoturn", "cloudstorage", "externalkeyboard", "hotkeys",
        "httpinspector", "japanese", "movetoarchive", "newsdownloader", "opds",
        "perceptionexpander", "qrclipboard", "wallabag", "timesync", "terminal",
    } do
        disabled[name] = true
    end
    G_reader_settings:saveSetting("plugins_disabled", disabled)
    G_reader_settings:makeTrue("speed_tweaks_applied")
end
