# Deploying PellMon to a Raspberry Pi (Docker)

Nothing in this guide has been run on a real Pi or against a real burner yet.
Follow `HARDWARE-BRINGUP.md` for the first supervised session.

## 1. Is a Raspberry Pi 3 Model A+ enough?

Probably yes, with two cautions. These are estimates, not measurements.

- **CPU:** quad-core Cortex-A53 at 1.4 GHz. PellMon polls a few values every few
  seconds and serves a small web UI, so CPU is not the constraint.
- **RAM: 512 MB is tight.** The Docker daemon plus two Python containers plus a
  D-Bus daemon should fit, but there is little headroom. Use Raspberry Pi OS
  **Lite** (no desktop) and add swap (section 5).
- **Building the image on the Pi is slow and memory-hungry.** Prefer building on
  your PC for the Pi's architecture and loading the finished image (section 5).
- **One USB port and no Ethernet.** A USB-serial adapter for a Scotte burner uses
  the only USB port. Networking is Wi-Fi. That is fine for the web UI and for NBE
  (network) burners, but see the NBE discovery note in section 4.

## 2. What to copy over SFTP

Copy these to a folder on the Pi, for example `/home/pi/pellmon/`:

- `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.dockerignore`
- `src/`, `data/`, `config/`
- `.env.example`

Do **not** copy: `venv-py3/`, `venv-wsl/`, `.git/`, `.planning/`, `.agent/`,
`.gemini/`, `.gsd/`, `Archive/`, `tests/`, or the `mqtt-*.json` file (it contains
device identifiers).

## 3. Install Docker on the Pi

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo usermod -aG docker $USER
```

Log out and back in, then check `docker compose version`.

## 4. Configure

```bash
cd ~/pellmon
cp .env.example .env
```

`.env` sets the timezone and ports. `PELLMON_WEB_HOST` should stay `0.0.0.0` under Docker.

Edit `config/pellmon.conf`. These points were checked against the code:

**a) Most settings live in `config/conf.d`.** Both daemons read every `*.conf` file
under `config_dir` after `pellmon.conf`. `docker-compose.yml` mounts `./config/conf.d`,
but that folder is not in the repo. Copy the whole shipped `src/conf.d` and fill in the
autotools placeholder (`@localstatedir@` becomes `/var`):

```bash
mkdir -p config/conf.d && cp -r src/conf.d/. config/conf.d/ && rm config/conf.d/Makefile.am && for f in config/conf.d/*.conf.in; do sed 's#@localstatedir@#/var#g' "$f" > "${f%.in}" && rm "$f"; done
```

This supplies the polling and graph sections (`database.conf`), the web UI settings
(`webinterface.conf`), and the default plugin list (`enabled_plugins.conf`). Then edit
the plugin file for your burner:

- Scotte (serial): `config/conf.d/plugins/scottecom.conf`, section `[plugin_ScotteCom]`,
  keys `serialport` and `chipversion` (`auto` or explicit). **For a Scotte burner on a
  USB serial adapter you normally only need to check that `serialport = /dev/ttyUSB0`
  matches the device name on the Pi** (step e).
- NBE (network): `config/conf.d/plugins/nbecom.conf`, section `[plugin_NBEcom]`,
  keys `serial` and `password`.

The `serialport` setting is read from that plugin file, not from `[conf]` in `pellmon.conf`.

**b) Enable plugins with `p01 = ScotteCom`, not `ScotteCom = yes`.** The key is
arbitrary and the **value** is the plugin name. The copied `enabled_plugins.conf`
already enables these:

```ini
[enabled_plugins]
p01 = ScotteCom
p06 = SiloLevel
p08 = Consumption
p09 = Cleaning
```

An entry like `NBEcom = yes` enables nothing, because the code takes the value (`yes`)
as the plugin name. If your own `config/pellmon.conf` uses that style, change it.
Extra plugins go in `pellmon.conf` under `[enabled_plugins]` in the same format.

**c) Passwords must be PBKDF2 hashes.** Generate one on any machine with the repo:

```bash
PYTHONPATH=src python3 -c "from Pellmonweb.auth import hash_password; print(hash_password('yourpassword'))"
```

Put it under `[authentication]` in `pellmon.conf` as `<username> = pbkdf2:sha256:600000$...`
(the key is the login name, the value is the hash).

**d) Polling needs `[pollvalues]`, `[rrd_ds_names]` and `[rrd_ds_types]`.** They are
supplied by `conf.d/database.conf` from step a. If they are missing, RRD polling is
disabled and only a log line says so.

**e) Serial access.** The compose file runs `pellmonsrv` as `privileged` with `/dev`
mounted read-only, so the serial device is visible inside the container. Confirm the
name on the Pi:

```bash
ls /dev/ttyUSB*
```

The daemon runs as a non-root user, so it also needs the **group that owns the device**.
Find its numeric id:

```bash
stat -c %g /dev/ttyUSB0
```

Put that number in `.env` as `SERIAL_GID` (the default is `20`, which is `dialout` on
Raspberry Pi OS; some adapters use another group, for example `46`):

```bash
echo "SERIAL_GID=46" >> .env
```

**Note:** with the wrong group the log shows `Could not open serial port ...
Permission denied`, and the main page shows the red "No connection to the burner"
banner with the reason; no burner values are served. Check the main page (no
banner) and the log (`serial port ok`, see troubleshooting) before believing any reading.

**f) NBE discovery (untested).** NBE discovery is a UDP broadcast to port 8483. The
default Docker bridge network usually does not forward broadcasts to your LAN. If the
controller is not found, try `network_mode: host` for the `pellmonsrv` service while
keeping the shared D-Bus socket volume. This has not been tried.

### Where PellMon keeps its data

Persistent data lives in a host folder, `${PELLMON_DATA_DIR:-./pellmon-data}`, with this layout:

- `pellmon-data/data/` - `rrd.db` (graphs) and `pellmon_settings.db` (settings changed in the GUI)
- `pellmon-data/logs/` - `pellmon.log` and the web logs

Set `PELLMON_DATA_DIR` in `.env` to an absolute path or a `./`-prefixed path (a bare name
becomes a Docker named volume, which is not what you want). The folder survives
`docker compose down -v` and Docker reinstalls, and it is gitignored. It must be on a
Linux filesystem (see section 7).

GUI-chosen settings (currently the system image picked on the Settings page) are stored in
`pellmon_settings.db` in this data folder. The daemon writes it, because the web container
mounts the folder read-only. The choice therefore survives `docker compose down -v` and
container recreation, and is included in backups.

A one-shot service, `pellmon-init`, runs as root before `pellmonsrv`. It creates the folders
and chowns only those data and log folders to 999:999 (the container user). It deliberately
does **not** touch `config/conf.d`: you keep editing `config/conf.d/*.conf` on the host (for
example over SFTP) as your normal user, with no `sudo`. `config/pellmon.conf` stays read-only
in both containers. If the data folder ever gets the wrong owner, re-run
`docker compose run --rm pellmon-init` (or `sudo chown -R 999:999 <PELLMON_DATA_DIR>`). Do not
`chmod -R 777` to work around it.

The config editor is the standalone `pellmonconf` tool on port 8083. It is **not started by
the compose stack today**. The writable `conf.d` mount and the "read-only" message for
`pellmon.conf` are in place for it, but nothing in `docker compose up` exercises them.
Note that writing `conf.d` from inside the container (uid 999) only works if those files are
writable by uid 999. Files owned by your host user are not, and that is intentional here; you
would have to grant that yourself (for example a group/ACL on `config/conf.d`) if you ever run
the editor in the container.

### Home Assistant / MQTT

PellMon can publish the burner to Home Assistant over MQTT (retained discovery, last will,
optional commands). It is the `HomeAssistant` plugin.

**Enable it.** New installs get it from the shipped `conf.d`. On an existing install add
this line to `config/conf.d/enabled_plugins.conf` and restart the containers:

```
p15 = HomeAssistant
```

Then open the **Home Assistant** page from the menu (`/homeassistant/`, login required).

**Broker host.** Enter the broker as an IP address or a DNS name. mDNS names such as
`homeassistant.local` usually do not resolve inside the container. If the broker runs on
the Docker host, add an `extra_hosts` entry (for example `host.docker.internal:host-gateway`)
to the `pellmonsrv` service and use that name. TLS is supported with certificate
verification against the image's CA store.

**Taking over the existing device.** Switch off the old publisher first, otherwise two
publishers fight over the same entities. Then read three values from Home Assistant
(Settings > Devices > the device > MQTT INFO, or the diagnostics download) and enter them
on the page: the `<device identifier>`, the discovery node id (the segment between the
component and the object id in its discovery topics) and the unique-id prefix (the part
before the object id). Save. History continues because the entity ids stay the same.
Optionally clear the old publisher's retained topics.

**Behaviour changes.**

- Burner ON and Burner OFF are no longer available from Home Assistant. PellMon clears their
  discovery entries; remove the leftover entities in Home Assistant if they remain.
- While "Allow commands from Home Assistant" is off, the ten setpoint numbers and the two
  reset buttons are removed from Home Assistant. They come back when it is switched on.
- Entities show unavailable when the burner is not connected, in demo mode, or when PellMon
  stops (the last will marks the device offline).

**Security.** The MQTT password is stored in the settings database (`pellmon_settings.db`)
on the data volume and is included in backups made with `tools/pellmon_backup.py`. Protect
the data folder and backup archives. Use a dedicated broker user whose ACL allows only the
topic prefix (default `scotte/#`) and the discovery prefix (`homeassistant/#`).

## 5. Build and start

**Option 1: build on your PC (recommended for a 3A+).** Use `linux/arm64` for a
64-bit Pi OS, or `linux/arm/v7` for a 32-bit one:

```bash
docker buildx build --platform linux/arm64 -t pellmon:latest --load .
```

```bash
docker save pellmon:latest | gzip > pellmon-image.tar.gz
```

Copy `pellmon-image.tar.gz` to the Pi over SFTP, then on the Pi:

```bash
gunzip -c pellmon-image.tar.gz | docker load
```

**Option 2: build on the Pi.** Add swap first, or the build may run out of memory:

```bash
sudo dphys-swapfile swapoff && sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile && sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

```bash
docker compose build
```

**Start:**

```bash
docker compose up -d
```

```bash
docker compose logs -f pellmonsrv
```

`pellmon-init` runs first and must show `Exited (0)` in `docker compose ps -a`. If the data
folder is unusable, `pellmonsrv` exits with a message naming `/var/lib/pellmon`
(`PELLMON_REQUIRE_DATADIR=1`) instead of silently running without persistence.

Healthy looks like:

- The log shows `Activated plugins: ScotteCom` (or your plugins).
- `docker compose ps` shows both containers healthy.
- The web UI answers at `http://<pi-ip>:8081`.

## 6. Updating, backups, troubleshooting

**Update:** re-copy `src/` (and `data/` if changed), then:

```bash
docker compose build && docker compose up -d
```

**Running the published image instead of building locally.** A Pi can run the
prebuilt multi-arch image `peterscholer74/pellmon:latest` (or a pinned
`peterscholer74/pellmon:{version}`) instead of building on-device or copying a
saved tarball. Set the `image:` value in `docker-compose.yml` to that reference;
then `docker compose pull && docker compose up -d` is what picks up a new
release (in place of the `docker compose build && docker compose up -d` update
command above, which is for the build-locally path). See
[`RELEASING.md`](RELEASING.md) for how and when new versions are published.

### Backup and restore

Run these from the repo root (the folder with `docker-compose.yml` and `config/`):

```bash
python3 tools/pellmon_backup.py backup --out pellmon-backup-$(date +%F).tar.gz
```

```bash
python3 tools/pellmon_backup.py restore pellmon-backup-<date>.tar.gz --yes
```

Restore stops the daemon, rebuilds the RRD with `rrdtool restore`, and restarts it. It works
PC to Pi because the RRD travels as an XML dump. The RRD and settings DB are built as temp
files, verified, and only then swapped in; the files they replace are kept as
`rrd.db.pre-restore` and `pellmon_settings.db.pre-restore` next to them (mode 0600, an older
`.pre-restore` is overwritten). If anything fails the originals stay in place and the service
is started again. With `--local` (direct paths, no docker) restore asks for confirmation too,
or pass `--yes`. A backup never overwrites an existing `--out` file.

The archive's `pellmon_settings.db` carries the GUI settings, so a restore also brings back
the chosen system image along with the plugin settings, with no separate step.

The archive is mode 0600 and contains the password hashes and the settings DB: keep it
private and never email it or put it on shared storage.

Prior to the `pellmon-dbus` service split, a restore's daemon restart put the bus on a new
socket and required `docker compose restart pellmonweb` afterward (the web page showed
"server not running" until you did). The D-Bus daemon now runs as its own long-lived
`pellmon-dbus` service, independent of `pellmonsrv`'s container lifecycle, so a plain
`pellmonsrv` restart (restore included) should no longer strand pellmonweb's connection.
If the web page still shows "server not running" after a restore, `docker compose restart
pellmonweb` remains the fallback.

**Why the working directory matters:** the RRD path comes from `config/conf.d/database.conf`
(`/var/lib/pellmon/rrd.db`), which overrides `config/pellmon.conf`. `[conf] config_dir` is the
*container* path `/etc/pellmon/conf.d`, so the tool reads the host copy `./config/conf.d` next to
`pellmon.conf` (even if a directory `/etc/pellmon/conf.d` also exists on the host; only
`--local` trusts the configured path). From another directory pass `--config /path/to/config/pellmon.conf`; if your
`conf.d` is elsewhere, pass `--host-config-dir /path/to/conf.d`. Add `--verbose` to see which
directory and RRD path were resolved. If no `database` value can be found the tool exits 1 with
a message naming the config file; it never guesses.

The backup archive also contains the MQTT password (see Home Assistant / MQTT above); store it accordingly.

### Moving data off the old named volume (one time)

Older deployments kept data in a Docker named volume. Find its name with `docker volume ls`,
then copy it once into the new folder. Create the folders first and run the copy as root
inside the container, so it can write there and hand the files to the container user:

```bash
mkdir -p pellmon-data/data pellmon-data/logs
```

```bash
docker run --rm --user root -v <project>_pellmon-data:/from -v "$PWD/pellmon-data/data":/to pellmon:latest sh -c 'cp -a /from/. /to/ && chown -R 999:999 /to'
```

```bash
docker compose up -d
```

`pellmon-init` fixes the ownership. A raw copy is only valid on the same machine type; for
PC to Pi use the backup tool instead.

**No items appear:**

- Look for `Activated plugins:` in the log. If it is missing, check the
  `[enabled_plugins]` format (4b).
- Search the log for `Unable to execute the code in plugin`.

**Cannot log in:** the password in `[authentication]` is probably not a hash (4c).

**Cannot reach the UI:** check `PELLMON_WEB_HOST` and `PELLMON_WEB_PORT` in `.env`,
and that the Pi's firewall allows the port.

**No values / serial permission or device errors:** look at the main page first.
A red banner "No connection to the burner" (with the reason underneath) means the
serial port cannot be opened or the burner is not answering; in that state no burner
values are served at all. A yellow "Demo mode: values are simulated" banner means
`serialport` is not set. If the banner names a permission or missing-device error,
confirm the device name (4e), that `serialport` matches it, and that `SERIAL_GID` in
`.env` is the device's group.

**Where the daemon's own log is.** The daemon writes its log to
`/var/log/pellmon/pellmon.log` inside the container, so `docker compose logs` does not
show plugin activation or serial messages. Read it with:

```bash
docker compose exec pellmonsrv tail -60 /var/log/pellmon/pellmon.log
```

If the container is stopped or restarting, read it directly on the host:

```bash
tail -40 "${PELLMON_DATA_DIR:-./pellmon-data}/logs/pellmon.log"
```

Look for `Activated plugins:` and then `serial port ok`. `Could not open serial port`
means the permission or device problem above; the main page then shows the red "No
connection to the burner" banner and no burner values are served.

**Log level and log size.** The daemon logs at `info` by default. `debug` logs every
serial frame (dozens of lines per poll), which fills the log folder quickly, adds CPU load
and wears an SD card, so use it only while troubleshooting: set `loglevel = debug` under
`[conf]` in `config/pellmon.conf`, then `docker compose restart pellmonsrv`, and set it back
to `info` afterwards. There is no log rotation yet, so check the size now and then:

```bash
ls -lh "${PELLMON_DATA_DIR:-./pellmon-data}/logs/"
```

**`Fontconfig error: No writable cache directories`** spam in `docker compose logs`
comes from `rrdtool graph` and is fixed by `XDG_CACHE_HOME=/tmp` in the compose file.

**Serial timeouts.** A log full of `Timeout`, `Retrying`, `answer was empty` and
`give up` means the port opened but the burner is not answering (the main page shows
the "No connection to the burner" banner after a few failed polls). That is a cabling or
adapter problem, not software: check that the adapter is RS232 (not 3.3 V/5 V TTL) if
the burner port is RS232, whether TX and RX are swapped (a null-modem cable or adapter
may be needed), and that the settings are 9600 baud, 8N1, no flow control. Test the
adapter itself with a loopback: stop the daemon, disconnect the burner, connect the
adapter's TX and RX pins together, and run (replace `/dev/ttyUSB0` with your `serialport`; the
group id is read from the device, the same value as `SERIAL_GID` in `.env`):

```bash
docker compose stop pellmonsrv
```

```bash
docker run --rm --group-add "$(stat -c %g /dev/ttyUSB0)" --device /dev/ttyUSB0 --entrypoint python3 pellmon:latest -c "import serial; s=serial.Serial('/dev/ttyUSB0',9600,timeout=1); s.write(b'hello'); print(s.read(5))"
```

It should print `b'hello'`. `b''` means the adapter or the Pi port is at fault.

**Editing `docker-compose.yml`.** Avoid broad `sed` replacements on it. The daemon's
`dbus-daemon` command needs `--session --address=`, while the health check's
`dbus-send` needs `--bus=`; a blanket replacement of one breaks the other and puts the
container in a restart loop. Use `.env` for settings such as `SERIAL_GID` instead.

## 7. Caveats

- Run on a Pi 3A+ only as far as daemon start-up, the web containers and opening the
  serial port. Communication with the burner itself is **not yet verified**.
- RAM use on the Pi is only roughly known: about 240 MiB was available with the daemon
  container running (some swap in use); it was not measured with the web container up.
- Protocol code is verified against a simulator only, not a real burner.
- `chown` is a no-op on Docker Desktop Windows/macOS mounts, so the data folder must live on
  a Linux filesystem (ext4, or the Pi).
- There is no backup button in the web GUI yet (deferred); use `tools/pellmon_backup.py`.
- The config editor is not part of the compose stack (section 4).
