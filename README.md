# Kindle setup

Kindle Paperwhite 5 (FW 5.18.6, jailbroken), KOReader only. Live copies of everything custom.

| Here | On the Kindle |
|---|---|
| `koreader/plugins/kindlehome.koplugin` | `/mnt/us/koreader/plugins/` (Kindle-style home screen, quick settings, reading stats) |
| `koreader/patches/*.lua` | `/mnt/us/koreader/patches/` (settings applied at start; see each file's header) |
| `koreader/settings/directory_defaults.lua` | `/mnt/us/koreader/settings/` (per-folder first-open defaults: Manga = right-to-left, dithering) |
| `system/koreader-autostart.conf` | `/etc/upstart/` (rootfs: `mntroot rw` first). Kill switch: `NO_KOREADER_AUTOSTART` file on the USB drive |
| `system/tz-Europe-Zagreb` | `/var/local/system/tz` (stock tz was a broken fixed GMT+01:46) |
| `backup/backup-out.sh` | `/mnt/us/koreader/backup-out.sh` |
| `backup/pi-backup.sh` | Pi `~/kindle-backup/backup.sh`, cron every 15 min |

SSH: `ssh -p 2222 root@192.168.1.119` (KOReader's dropbear, key-only).

Daily backups of settings, stats, highlights, plugin and patches are on the Pi in
`~/kindle-backup/kindle-YYYY-MM-DD.tar.gz` (newest 30). Restore: copy the tarball to the
Kindle and `tar xzf` it in `/mnt/us` with KOReader closed. `backup/setup-kindle-backup.sh`
redoes the Pi side from scratch.

## Manga

`tools/manga_convert.py in.cbz "out/Title, Vol. N - Author.cbz"` (needs Pillow) converts a CBZ (or a folder of page images; for PDFs extract them first with `pdfimages -j book.pdf dir/p`) to
greyscale pages fitted to the PW5's 1236x1648 screen, in natural chapter/page order. Put the result
under `/mnt/us/documents/Manga/` so it gets the manga defaults; `2-comics.lua` flashes every 2 pages
while a comic is open.
