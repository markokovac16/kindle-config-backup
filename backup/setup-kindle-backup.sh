#!/bin/sh
# One-time setup: the Raspberry Pi pulls a daily backup of the Kindle's KOReader setup.
# 1. Kindle: script that streams the backup as tar.gz.
# 2. Pi: its own SSH key, allowed on the Kindle ONLY to run that script (forced command, no shell).
# 3. Pi: puller script + cron every 15 min (backs up once per ~20h when the Kindle is awake on Wi-Fi).
set -e
S=$(dirname "$0")
scp -q -P 2222 $S/backup-out.sh root@192.168.1.119:/mnt/us/koreader/backup-out.sh
ssh rpi 'mkdir -p ~/kindle-backup; [ -f ~/.ssh/kindle_backup ] || ssh-keygen -q -t ed25519 -N "" -C "rpi kindle-backup" -f ~/.ssh/kindle_backup'
KEY=$(ssh rpi 'cat ~/.ssh/kindle_backup.pub')
ssh -n -p 2222 root@192.168.1.119 "cd /mnt/us/koreader/settings/SSH && cp authorized_keys authorized_keys.bak && { grep -q 'kindle-backup' authorized_keys || echo 'command=\"sh /mnt/us/koreader/backup-out.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $KEY' >> authorized_keys; }"
scp -q $S/pi-backup.sh rpi:kindle-backup/backup.sh
ssh rpi 'chmod +x ~/kindle-backup/backup.sh; (crontab -l 2>/dev/null | grep -v kindle-backup; echo "*/15 * * * * $HOME/kindle-backup/backup.sh") | crontab -; ~/kindle-backup/backup.sh; ls -la ~/kindle-backup'
