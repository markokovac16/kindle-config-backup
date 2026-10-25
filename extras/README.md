# Extras

Not installed on the Kindle; kept for fun.

- `doom.koplugin`: DOOM (shareware E1) as a KOReader plugin. Copy the folder to `/mnt/us/koreader/plugins/`, restart KOReader, open it from the main menu (More tools -> DOOM). Rebuild with `doom-build/build.sh` (doomgeneric + `doomgeneric-koreader.patch`, crosstool-NG armhf GCC; zig builds crash dlopen on the Kindle glibc 2.20).

## interactive-fiction/

Interactive Fiction plugin (frotz.koplugin 3.0.1, github kbarni/frotz.koplugin) plus Zork I–III
(MIT, from github historicalsource). Works fully offline. Removed from the Kindle 2026-10-25 because
Marko didn't want it. To reinstall: copy `frotz.koplugin` to `koreader/plugins/`, `chmod +x
binaries/armhf/*`, copy `ifgames/` to `koreader/ifgames/`. The home "Extras" entry with a game picker
is in kindlehome git history (commit "Home: fix Text adventures game list crash").
