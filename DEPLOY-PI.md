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

**Warning:** with the wrong group the log shows `Could not open serial port ...
Permission denied`, and the Scotte plugin then **silently falls back to a dummy device
that produces fake values**. The web UI looks normal. Always check the log for
`serial port ok` (see troubleshooting) before believing any reading.

**f) NBE discovery (untested).** NBE discovery is a UDP broadcast to port 8483. The
default Docker bridge network usually does not forward broadcasts to your LAN. If the
controller is not found, try `network_mode: host` for the `pellmonsrv` service while
keeping the shared D-Bus socket volume. This has not been tried.

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

Healthy looks like:

- The log shows `Activated plugins: ScotteCom` (or your plugins).
- `docker compose ps` shows both containers healthy.
- The web UI answers at `http://<pi-ip>:8081`.

## 6. Updating, backups, troubleshooting

**Update:** re-copy `src/` (and `data/` if changed), then:

```bash
docker compose build && docker compose up -d
```

**Backup:** the RRD database lives in the `pellmon-data` volume (Docker prefixes the
name with the project folder name). Keep a copy before upgrades.

**No items appear:**

- Look for `Activated plugins:` in the log. If it is missing, check the
  `[enabled_plugins]` format (4b).
- Search the log for `Unable to execute the code in plugin`.

**Cannot log in:** the password in `[authentication]` is probably not a hash (4c).

**Cannot reach the UI:** check `PELLMON_WEB_HOST` and `PELLMON_WEB_PORT` in `.env`,
and that the Pi's firewall allows the port.

**Serial permission or device errors:** confirm the device name (4e), that
`serialport` matches it, and that `SERIAL_GID` in `.env` is the device's group.

**Where the daemon's own log is.** The daemon writes its log to
`/var/log/pellmon/pellmon.log` inside the container, so `docker compose logs` does not
show plugin activation or serial messages. Read it with:

```bash
docker compose exec pellmonsrv tail -60 /var/log/pellmon/pellmon.log
```

If the container is stopped or restarting, read it from the volume instead:

```bash
docker run --rm -v pellmon_pellmon-logs:/var/log/pellmon --entrypoint tail pellmon:latest -40 /var/log/pellmon/pellmon.log
```

Look for `Activated plugins:` and then `serial port ok`. `Could not open serial port`
means the permission or device problem above, and the values shown are fake.

**`Fontconfig error: No writable cache directories`** spam in `docker compose logs`
comes from `rrdtool graph` and is fixed by `XDG_CACHE_HOME=/tmp` in the compose file.

**Serial timeouts.** A log full of `Timeout`, `Retrying`, `answer was empty` and
`give up` means the port opened but the burner is not answering. That is a cabling or
adapter problem, not software: check that the adapter is RS232 (not 3.3 V/5 V TTL) if
the burner port is RS232, whether TX and RX are swapped (a null-modem cable or adapter
may be needed), and that the settings are 9600 baud, 8N1, no flow control. Test the
adapter itself with a loopback: stop the daemon, disconnect the burner, connect the
adapter's TX and RX pins together, and run (use your `SERIAL_GID` in place of `46`):

```bash
docker compose stop pellmonsrv
```

```bash
docker run --rm --group-add 46 --device /dev/ttyUSB0 --entrypoint python3 pellmon:latest -c "import serial; s=serial.Serial('/dev/ttyUSB0',9600,timeout=1); s.write(b'hello'); print(s.read(5))"
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
