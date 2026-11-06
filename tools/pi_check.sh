#!/usr/bin/env bash
# PellMon deployment check, run on the Pi (the Docker host) from anywhere:
#
#   tools/pi_check.sh [--repo DIR] [--backup-dir DIR] [--data-dir DIR] [--web-url URL]
#                     [--skip-restore] [--logs N] [--no-color]
#
# It only READS: it never changes your data, settings or containers. The one thing it writes is a
# tiny temporary file in the backup folder (and /tmp inside the container) to prove the daemon user
# can write there, and it removes it again. Exit status is 1 when something failed, 0 otherwise.
#
# What it checks: containers and image version, the daemon log (plugins, tracebacks, Backup lines),
# the backup folder (mounted? other disk than the data? writable by the container user? free space),
# the Backup plugin's stored settings and last result, and the newest archive (readable, complete,
# and a real `rrdtool restore` of its RRD dump in a scratch folder), the live RRD and settings
# database, and the web pages. Things only a person can do (unplug the NAS, watch Home Assistant)
# are listed at the end.
#
# Archives are mode 0600 owned by uid 999, so the host user usually cannot read them: archive checks
# run inside the container. Docker needs to be usable by your user (docker group, or run with sudo).

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# the checkout: the folder above tools/, or the script's own folder when it was copied next to docker-compose.yml
if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    REPO=$SCRIPT_DIR
else
    REPO=$(dirname "$SCRIPT_DIR")
fi
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
SRV=pellmonsrv
WEB=pellmonweb
DBUS=pellmon-dbus
BACKUP_DIR=""
DATA_DIR=""
WEB_URL=""
SKIP_RESTORE=0
LOG_LINES=1000
USE_COLOR=1

usage() {
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO=$2; shift 2 ;;
        --backup-dir) BACKUP_DIR=$2; shift 2 ;;
        --data-dir) DATA_DIR=$2; shift 2 ;;
        --web-url) WEB_URL=$2; shift 2 ;;
        --skip-restore) SKIP_RESTORE=1; shift ;;
        --logs) LOG_LINES=$2; shift 2 ;;
        --no-color) USE_COLOR=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then
    USE_COLOR=0
fi
if [ "$USE_COLOR" = 1 ]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_FAIL=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_FAIL=""; C_DIM=""; C_OFF=""
fi

N_OK=0; N_WARN=0; N_FAIL=0
WARNINGS=(); FAILURES=()

section() { printf '\n== %s ==\n' "$1"; }
ok()   { N_OK=$((N_OK + 1));     printf '%s[ OK ]%s %s\n' "$C_OK" "$C_OFF" "$1"; }
warn() { N_WARN=$((N_WARN + 1)); WARNINGS+=("$1"); printf '%s[WARN]%s %s\n' "$C_WARN" "$C_OFF" "$1"; }
fail() { N_FAIL=$((N_FAIL + 1)); FAILURES+=("$1"); printf '%s[FAIL]%s %s\n' "$C_FAIL" "$C_OFF" "$1"; }
info() { printf '%s       %s%s\n' "$C_DIM" "$1" "$C_OFF"; }

# value of KEY in .env (last assignment, quotes stripped), empty when absent
envval() {
    local f="$REPO/.env" v
    [ -f "$f" ] || return 0
    v=$(grep -E "^[[:space:]]*$1=" "$f" | tail -n 1 | cut -d= -f2- | tr -d '\r')
    v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}
    printf '%s' "$v"
}

# run a shell snippet inside a container (as its own user), stdin is passed through
cexec() { "$DOCKER" exec -i "$1" sh -c "$2" 2>&1; }

abspath() {
    case "$1" in
        /*) printf '%s' "$1" ;;
        *) printf '%s/%s' "$REPO" "${1#./}" ;;
    esac
}

summary() {
    section "Summary"
    printf '%s ok, %s warnings, %s failures\n' "$N_OK" "$N_WARN" "$N_FAIL"
    if [ "$N_FAIL" -gt 0 ]; then
        printf '\nFailures:\n'
        for m in "${FAILURES[@]}"; do printf '  - %s\n' "$m"; done
    fi
    if [ "$N_WARN" -gt 0 ]; then
        printf '\nWarnings:\n'
        for m in "${WARNINGS[@]}"; do printf '  - %s\n' "$m"; done
    fi
    cat <<'EOF'

Still to do by hand (this script cannot do these):
  1. Backup page: Test folder, Back up now, set a schedule a few minutes ahead and watch it run.
  2. Retention: keep 2 / 0 weeks, make 3 backups, check the oldest is deleted.
  3. Unmount the NAS, recreate the containers: the page must say "same disk" or "folder missing".
  4. Unplug the NAS: the Backup page must still load in a few seconds with a warning.
  5. Stop pellmonsrv across a scheduled time and start it: a backup is made within a couple of minutes.
  6. Home Assistant: new entities, Allow commands round trip, dashboard YAML renders.
  7. Compare the silo days-left value and the consumption bars with what you expect.
  8. A real restore (on a copy or when you can afford it): tools/pellmon_backup.py restore FILE --yes.
EOF
}

# ---------------------------------------------------------------- 1. host and stack
section "Docker and containers"

if ! command -v "$DOCKER" >/dev/null 2>&1; then
    fail "docker is not installed or not on PATH ($DOCKER)"
    summary
    exit 1
fi
if ! "$DOCKER" info >/dev/null 2>&1; then
    fail "cannot talk to the Docker daemon (add your user to the docker group, or run this with sudo)"
    summary
    exit 1
fi
ok "Docker is reachable"

for c in "$DBUS" "$SRV" "$WEB"; do
    st=$("$DOCKER" inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}|{{.RestartCount}}' "$c" 2>/dev/null)
    if [ -z "$st" ]; then
        fail "container $c does not exist (docker compose up -d)"
        continue
    fi
    status=${st%%|*}; rest=${st#*|}; health=${rest%%|*}; restarts=${rest#*|}
    if [ "$status" != "running" ]; then
        fail "container $c is $status"
    elif [ "$health" = "unhealthy" ]; then
        fail "container $c is running but unhealthy"
    elif [ "$health" = "starting" ]; then
        warn "container $c is still starting"
    else
        ok "container $c is running${health:+ ($health)}"
    fi
    if [ "${restarts:-0}" -gt 3 ] 2>/dev/null; then
        warn "container $c has restarted $restarts times (docker logs $c)"
    fi
done

image_ver=$(cexec "$SRV" 'cat /app/VERSION' | head -n 1 | tr -d '[:space:]')
repo_ver=""
[ -f "$REPO/VERSION" ] && repo_ver=$(tr -d '[:space:]\r' < "$REPO/VERSION")
if [ -n "$image_ver" ]; then
    ok "pellmonsrv image version: $image_ver"
    if [ -n "$repo_ver" ] && [ "$image_ver" != "$repo_ver" ]; then
        warn "image is $image_ver but this checkout says $repo_ver (docker compose pull / git pull, then up -d)"
    elif [ -z "$repo_ver" ]; then
        info "no VERSION file in $REPO: this does not look like a full checkout (docker-compose.yml, .env and tools/ should be there)"
    fi
else
    warn "could not read the image version from the pellmonsrv container"
fi
tz=$(cexec "$SRV" 'date +"%Z %z"' | head -n 1)
[ -n "$tz" ] && info "server time zone in the container: $tz (backup times use it; set TZ in .env)"

# ---------------------------------------------------------------- 2. daemon log
section "Daemon log (/var/log/pellmon/pellmon.log, last $LOG_LINES lines)"

# the daemon writes /var/log/pellmon/pellmon.log (docker logs only has what goes to stderr)
logs=$(cexec "$SRV" "tail -n $LOG_LINES /var/log/pellmon/pellmon.log 2>/dev/null")
if [ -z "$logs" ]; then
    info "no /var/log/pellmon/pellmon.log in the container, using docker logs instead"
    logs=$("$DOCKER" logs --tail "$LOG_LINES" "$SRV" 2>&1)
fi
plugins=$(cexec "$SRV" "grep -h 'Activated plugins:' /var/log/pellmon/pellmon.log* 2>/dev/null | tail -n 1")
[ -z "$plugins" ] && plugins=$(printf '%s\n' "$logs" | grep -E 'Activated plugins:' | tail -n 1)
if [ -z "$plugins" ]; then
    warn "no 'Activated plugins:' line in /var/log/pellmon/pellmon.log (rotated away, or the daemon failed to start: View log in the web interface)"
else
    info "$plugins"
    for p in Backup HomeAssistant Openweathermap; do
        if printf '%s' "$plugins" | grep -q "$p"; then
            ok "plugin $p is active"
        else
            fail "plugin $p is not active (old image? recreate: docker compose up -d --force-recreate pellmonsrv)"
        fi
    done
fi
failed=$(printf '%s\n' "$logs" | grep -E 'Failed to activate plugins:' | tail -n 1)
[ -n "$failed" ] && warn "$failed"
tb=$(printf '%s\n' "$logs" | grep -c 'Traceback')
if [ "$tb" -gt 0 ]; then
    warn "$tb traceback(s) in the daemon log (docker logs $SRV | grep -B2 -A12 Traceback)"
else
    ok "no tracebacks in the daemon log"
fi
backup_lines=$(printf '%s\n' "$logs" | grep -E 'Backup (written|failed|scheduler error|could not)' | tail -n 5)
if [ -n "$backup_lines" ]; then
    info "recent Backup log lines:"
    printf '%s\n' "$backup_lines" | while IFS= read -r l; do info "  $l"; done
fi

# ---------------------------------------------------------------- 3. backup folder, host side
section "Backup folder (host)"

[ -z "$BACKUP_DIR" ] && BACKUP_DIR=$(envval PELLMON_BACKUP_DIR)
[ -z "$BACKUP_DIR" ] && BACKUP_DIR=./pellmon-backups
BACKUP_DIR=$(abspath "$BACKUP_DIR")
[ -z "$DATA_DIR" ] && DATA_DIR=$(envval PELLMON_DATA_DIR)
[ -z "$DATA_DIR" ] && DATA_DIR=./pellmon-data
DATA_DIR=$(abspath "$DATA_DIR")/data
info "PELLMON_BACKUP_DIR = $BACKUP_DIR"

if [ ! -d "$BACKUP_DIR" ]; then
    fail "backup folder $BACKUP_DIR does not exist on the host (mount the NAS or create it)"
else
    ok "backup folder exists"
    fstype=$(stat -f -c %T "$BACKUP_DIR" 2>/dev/null)
    [ -n "$fstype" ] && info "filesystem type: $fstype"
    if command -v mountpoint >/dev/null 2>&1 && mountpoint -q "$BACKUP_DIR"; then
        ok "it is a mount point (a separate filesystem)"
    else
        warn "it is not a mount point itself: if the NAS/USB drive is not mounted here the backups land on the SD card"
    fi
    bdev=$(stat -c %d "$BACKUP_DIR" 2>/dev/null)
    ddev=$(stat -c %d "$DATA_DIR" 2>/dev/null)
    if [ -z "$ddev" ]; then
        warn "data folder $DATA_DIR not found, cannot compare disks"
    elif [ "$bdev" = "$ddev" ]; then
        fail "backup folder is on the SAME disk as the data ($DATA_DIR): not mounted? the plugin refuses to back up here"
    else
        ok "backup folder is on a different disk than the data"
    fi
    free_kb=$(df -Pk "$BACKUP_DIR" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_kb" ]; then
        free_mb=$((free_kb / 1024))
        if [ "$free_mb" -lt 200 ]; then
            warn "only ${free_mb} MB free in the backup folder"
        else
            ok "free space: ${free_mb} MB"
        fi
    fi
    info "owner uid:gid and mode on the host: $(stat -c '%u:%g %a' "$BACKUP_DIR" 2>/dev/null) (the container writes as uid 999)"
fi

# ---------------------------------------------------------------- 4. backup folder, container side
section "Backup folder (inside $SRV, as the daemon user)"

uid=$(cexec "$SRV" 'id -u' | head -n 1)
info "container user uid: ${uid:-unknown}"
if cexec "$SRV" 'test -d /backups' >/dev/null; then
    ok "/backups is mounted in the container"
    if out=$(cexec "$SRV" 'f=/backups/.pi-check-$$; echo ok > "$f" && rm -f "$f"'); then
        ok "the daemon user can create and delete files in /backups"
    else
        fail "the daemon user (uid ${uid:-999}) cannot write to /backups: $out (chown 999:999, NFS export, or uid=999 for CIFS)"
    fi
    if cexec "$SRV" 'a=$(stat -c %d /backups); b=$(stat -c %d /var/lib/pellmon); [ "$a" != "$b" ]' >/dev/null; then
        ok "inside the container /backups is on another disk than /var/lib/pellmon"
    else
        fail "inside the container /backups is on the same disk as /var/lib/pellmon (recreate after mounting: docker compose up -d --force-recreate pellmonsrv)"
    fi
else
    fail "/backups is not mounted in the container (old compose file? docker compose up -d --force-recreate pellmon-init pellmonsrv)"
fi
rrdv=$(cexec "$SRV" 'rrdtool --version | head -n 1')
case "$rrdv" in
    RRDtool*) ok "rrdtool in the container: $rrdv" ;;
    *) fail "rrdtool is not usable in the container: $rrdv" ;;
esac

# ---------------------------------------------------------------- 5. plugin state
section "Backup plugin settings and last result"

PYSTATE=$(cat <<'EOF'
import json, sqlite3, time
c = sqlite3.connect('file:/var/lib/pellmon/pellmon_settings.db?mode=ro', uri=True)
def get(key):
    r = c.execute('select value from keyval where id=?', (key,)).fetchone()
    try:
        return json.loads(r[0]) if r and r[0] else None
    except Exception:
        return {}
cfg, st = get('backup.config'), get('backup.state')
print('CONFIGURED=%d' % (cfg is not None))
if cfg:
    for k in ('enabled', 'frequency', 'time', 'weekday', 'keep_daily', 'keep_weekly', 'subfolder', 'require_other_disk'):
        print('CFG_%s=%s' % (k, cfg.get(k)))
if st:
    now = time.time()
    for k in ('last_file', 'last_size', 'reason'):
        print('ST_%s=%s' % (k, st.get(k)))
    for k in ('last_ok', 'last_attempt'):
        v = st.get(k)
        print('ST_%s_AGE_H=%s' % (k, ('%.1f' % ((now - v) / 3600.0)) if v else ''))
EOF
)
state=$(printf '%s\n' "$PYSTATE" | "$DOCKER" exec -i "$SRV" python3 - 2>&1)
field() { printf '%s\n' "$state" | sed -n "s/^$1=//p" | head -n 1; }
if ! printf '%s\n' "$state" | grep -q '^CONFIGURED='; then
    warn "could not read the plugin settings from the settings database: $(printf '%s' "$state" | head -n 1)"
elif [ "$(field CONFIGURED)" = "0" ]; then
    info "the Backup page has never been saved: defaults apply, automatic backups are off"
else
    enabled=$(field CFG_enabled); freq=$(field CFG_frequency)
    info "enabled=$enabled $freq at $(field CFG_time), keep $(field CFG_keep_daily) + $(field CFG_keep_weekly) weekly, folder '/backups/$(field CFG_subfolder)', other-disk required: $(field CFG_require_other_disk)"
    if [ "$enabled" = "True" ]; then
        ok "automatic backups are enabled"
        age=$(field ST_last_ok_AGE_H)
        limit=36; [ "$freq" = "weekly" ] && limit=192
        if [ -z "$age" ]; then
            warn "enabled but no successful backup recorded yet"
        elif awk -v a="$age" -v l="$limit" 'BEGIN{exit !(a > l)}'; then
            warn "last successful backup was ${age} h ago (more than the schedule should allow)"
        else
            ok "last successful backup ${age} h ago: $(field ST_last_file)"
        fi
    else
        info "automatic backups are off (manual Back up now still works)"
        age=$(field ST_last_ok_AGE_H)
        [ -n "$age" ] && info "last successful backup ${age} h ago"
    fi
    reason=$(field ST_reason)
    if [ -n "$reason" ] && [ "$reason" != "None" ] && [ "$reason" != "" ]; then
        fail "the last backup attempt failed: $reason"
    fi
fi

# ---------------------------------------------------------------- 6. archives
section "Archives"

list=$(cexec "$SRV" "find /backups -maxdepth 3 -type f -name 'pellmon-backup-*.tar.gz' -printf '%T@ %s %m %p\n' 2>/dev/null | sort -rn")
count=$(printf '%s\n' "$list" | grep -c 'pellmon-backup-')
if [ "$count" -eq 0 ]; then
    warn "no backup archives in /backups yet (press Back up now on the Backup page)"
else
    ok "$count archive(s) in /backups"
    newest=$(printf '%s\n' "$list" | head -n 1)
    set -- $newest
    nsize=$2; nmode=$3; npath=$4
    info "newest: $npath ($((nsize / 1024)) kB, mode $nmode)"
    [ "$nmode" != "600" ] && warn "archive mode is $nmode, not 600 (some NAS filesystems cannot hold 0600; keep the share private)"
    if cexec "$SRV" "gzip -t '$npath'" >/dev/null; then
        ok "newest archive passes gzip -t"
    else
        fail "newest archive is damaged (gzip -t failed)"
    fi
    members=$(cexec "$SRV" "tar tzf '$npath'")
    for m in rrd.xml pellmon_settings.db manifest.json; do
        if printf '%s\n' "$members" | grep -qx "$m"; then
            ok "archive contains $m"
        else
            fail "archive is missing $m"
        fi
    done
    printf '%s\n' "$members" | grep -q '^config/' && ok "archive contains the config folder" || warn "archive has no config folder"

    if [ "$SKIP_RESTORE" = 1 ]; then
        info "restore round trip skipped (--skip-restore)"
    else
        info "restore round trip in a scratch folder (extracts rrd.xml, which can be 100 MB+; the live data is not touched)"
        out=$(cexec "$SRV" "d=/tmp/pi-check.\$\$ && mkdir -p \$d && tar xzf '$npath' -C \$d rrd.xml pellmon_settings.db && rrdtool restore \$d/rrd.xml \$d/t.rrd && rrdtool info \$d/t.rrd | sed -n '1,3p' && python3 -c \"import sqlite3;print('settings integrity:',sqlite3.connect('\$d/pellmon_settings.db').execute('pragma integrity_check').fetchone()[0])\"; rc=\$?; rm -rf \$d; exit \$rc")
        rc=$?
        if [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'settings integrity: ok'; then
            ok "rrdtool restore of the archive works and the settings database is intact"
            printf '%s\n' "$out" | head -n 3 | while IFS= read -r l; do info "  $l"; done
        else
            fail "restore round trip failed: $(printf '%s' "$out" | tail -n 3 | tr '\n' ' ')"
        fi
    fi
fi

# ---------------------------------------------------------------- 7. live data
section "Live data"

last=$(cexec "$SRV" 'rrdtool last /var/lib/pellmon/rrd.db')
now=$(cexec "$SRV" 'date +%s' | head -n 1)
if printf '%s' "$last" | grep -qE '^[0-9]+$' && printf '%s' "$now" | grep -qE '^[0-9]+$'; then
    age=$((now - last))
    if [ "$age" -gt 600 ]; then
        warn "the RRD was last updated ${age} s ago (burner not connected, or polling stopped)"
    else
        ok "the RRD is being updated (last update ${age} s ago)"
    fi
else
    warn "could not read the RRD last-update time: $(printf '%s' "$last" | head -n 1)"
fi
mode=$(cexec "$SRV" 'stat -c %a /var/lib/pellmon/pellmon_settings.db' | head -n 1)
if [ "$mode" = "600" ]; then
    ok "settings database mode is 600"
elif [ -n "$mode" ]; then
    warn "settings database mode is $mode (it holds password hashes and secrets; expected 600)"
fi

# ---------------------------------------------------------------- 8. web
section "Web interface"

[ -z "$WEB_URL" ] && WEB_URL="http://localhost:$(envval PELLMON_WEB_PORT)"
WEB_URL=$(printf '%s' "$WEB_URL" | tr -d '\r')
[ "$WEB_URL" = "http://localhost:" ] && WEB_URL="http://localhost:8081"
if ! command -v "$CURL" >/dev/null 2>&1; then
    warn "curl is not installed, web checks skipped"
else
    for page in "/" "/backup/" "/homeassistant/" "/weather/" "/settings/"; do
        code=$("$CURL" -s -o /dev/null -w '%{http_code}' --max-time 10 "$WEB_URL$page" 2>/dev/null)
        case "$code" in
            200) ok "$page answers 200" ;;
            301|302|303) ok "$page redirects ($code, normally to the login page)" ;;
            404) fail "$page answers 404 (the web container runs an image without this page: pull and recreate)" ;;
            000|"") fail "$page did not answer at $WEB_URL (container down, wrong port?)" ;;
            *) warn "$page answers $code" ;;
        esac
    done
fi

summary
[ "$N_FAIL" -eq 0 ]
