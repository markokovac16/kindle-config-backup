-- Auto warmth + dark mode by the sun in Zagreb (applied once; change under Settings -> Auto warmth).
-- Warmth points: midnight, astro/nautical/civil dawn, sunrise, noon, sunset, civil/nautical/astro dusk, midnight.
-- Values over 100 mean dark mode on at full warmth.
if not G_reader_settings:isTrue("night_light_applied") then
    G_reader_settings:saveSetting("autowarmth_activate", 1) -- follow the sun
    G_reader_settings:makeFalse("autowarmth_easy_mode")
    G_reader_settings:saveSetting("autowarmth_location", "Zagreb")
    G_reader_settings:saveSetting("autowarmth_latitude", 45.81)
    G_reader_settings:saveSetting("autowarmth_longitude", 15.98)
    G_reader_settings:saveSetting("autowarmth_altitude", 120)
    G_reader_settings:saveSetting("autowarmth_warmth", { 110, 110, 75, 50, 25, 0, 25, 50, 75, 110, 110 })
    G_reader_settings:makeTrue("autowarmth_control_warmth")
    G_reader_settings:makeTrue("autowarmth_control_nightmode")
    -- The quick settings Dark mode tile is a manual override, so no nag dialog on it.
    G_reader_settings:makeTrue("autowarmth_hide_nightmode_warning")
    G_reader_settings:makeTrue("night_light_applied")
end
