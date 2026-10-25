# DOOM for KOReader (Kindle PW5)

- `libdoom.so`: [doomgeneric](https://github.com/ozkl/doomgeneric) @ e257a09 (GPLv2) built for armhf / glibc 2.20 with crosstool-NG GCC 15.2.
  Every `exit()` in the engine is compiled as `doom_exit()`, which longjmps back into `doom_init`/`doom_tick`, so quitting
  or a fatal error never takes KOReader down. The engine can start once per KOReader run.
- `doom1.wad`: shareware DOOM v1.9 (SHA1 5b2e249b9c5133ec987b3ea77596381dc0d6bc1d), freely redistributable.
- Saves and config: `koreader/settings/doom/`.
- Rebuild: apply `doomgeneric-koreader.patch` and run `build.sh` (both kept in the backup repo next to this plugin).
