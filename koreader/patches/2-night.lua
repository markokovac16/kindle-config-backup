-- Auto warmth by the sun in Zagreb (applied once; change under Settings -> Auto warmth).
-- Warmth points: midnight, astro/nautical/civil dawn, sunrise, noon, sunset, civil/nautical/astro dusk, midnight.
if not G_reader_settings:isTrue("night_light_applied") then
    G_reader_settings:saveSetting("autowarmth_activate", 1) -- follow the sun
    G_reader_settings:makeFalse("autowarmth_easy_mode")
    G_reader_settings:saveSetting("autowarmth_location", "Zagreb")
    G_reader_settings:saveSetting("autowarmth_latitude", 45.81)
    G_reader_settings:saveSetting("autowarmth_longitude", 15.98)
    G_reader_settings:saveSetting("autowarmth_altitude", 120)
    G_reader_settings:saveSetting("autowarmth_warmth", { 100, 100, 75, 50, 25, 0, 25, 50, 75, 100, 100 })
    G_reader_settings:makeTrue("autowarmth_control_warmth")
    G_reader_settings:makeTrue("autowarmth_control_nightmode")
    -- The quick settings Dark mode tile is a manual override, so no nag dialog on it.
    G_reader_settings:makeTrue("autowarmth_hide_nightmode_warning")
    G_reader_settings:makeTrue("night_light_applied")
end

-- Marko didn't want dark mode switching on by itself: warmth only, dark mode stays manual.
if not G_reader_settings:isTrue("night_mode_schedule_off") then
    G_reader_settings:makeFalse("autowarmth_control_nightmode")
    G_reader_settings:saveSetting("autowarmth_warmth", { 100, 100, 75, 50, 25, 0, 25, 50, 75, 100, 100 })
    -- The screen was already inverted from the setting at startup, so un-invert it too,
    -- or the Dark mode tile ends up showing the opposite of the screen.
    local Screen = require("device").screen
    if Screen.night_mode then Screen:toggleNightMode() end
    G_reader_settings:makeFalse("night_mode")
    G_reader_settings:makeTrue("night_mode_schedule_off")
end
