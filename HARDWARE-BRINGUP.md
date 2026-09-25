# Hardware bring-up checklist

Pre-flight and first-connection checklist for running PellMon against a real
pellet burner (Scotte over serial, NBE over the network).

The Scotte and NBE protocol fixes are verified with mocked I/O only. Nothing in
this repo has yet been run against a physical burner, so treat the first
session as a supervised test, not a deployment.

## 1. Pre-flight

- [ ] Deploy the committed `master` (not a working tree with local edits).
- [ ] Replace the plaintext web password in `config/pellmon.conf` with a PBKDF2 hash.
      Plaintext passwords are no longer accepted, so without this you cannot log in.
      ```bash
      python3 -c "from Pellmonweb.auth import hash_password; print(hash_password('yourpassword'))"
      ```
      Put the result under `[authentication]` as `user = pbkdf2:sha256:600000$<salt>$<hash>`.
- [ ] Decide how the web UI is reached. It binds to `127.0.0.1` by default.
      Override with `[conf] host = ...` or the `PELLMON_WEB_HOST` env var.
      `docker-compose.yml` sets `0.0.0.0` for the container.
- [ ] Confirm `[rrd_ds_types]` (and the matching `[rrd_ds_names]`) exist in `pellmon.conf`.
      If they are missing, RRD polling is disabled and only a log line says so.
- [ ] `PELLMON_DATA_DIR` (default `./pellmon-data`) must exist on a Linux filesystem before
      the first start (chown does not work on Windows/macOS mounts).
- [ ] Back up the RRD database and the settings sqlite (keyval) database.
- [ ] Write down every setting currently on the burner, so you can restore it.
- [ ] Have the burner's own display/manual at hand as the reference for "correct" values.

## 2. Access to the burner

### Scotte (serial)

- [ ] Set `serialport` (e.g. `/dev/ttyUSB0`) and `chipversion` (`auto` or explicit)
      in `conf.d/plugins/scottecom.conf`.
      **If `serialport` is removed, the plugin runs on dummy data.** This is now labelled
      "Demo mode: values are simulated" on the main page. A `serialport` that is set but
      cannot be opened is an error state ("No connection to the burner"), not silent fake
      data. Values that look plausible are not proof you are talking to the burner.
- [ ] Confirm the main page shows no banner (or `burner_connection` reads `connected`)
      before trusting any number.
- [ ] The daemon user can open the device (bare metal: member of `dialout`).
- [ ] Docker: the compose file runs `pellmonsrv` as `privileged: true` and does not
      map a specific device. Confirm `/dev/ttyUSB0` is visible inside the container.

### NBE (network)

- [ ] Set `serial` and `password` in `conf.d/plugins/nbecom.conf`
      (the shipped file contains placeholder values).
- [ ] Discovery is a UDP broadcast to port 8483. Docker bridge networking and
      firewalls commonly block broadcasts. Test on the host network first if discovery fails.
- [ ] Controller and PellMon are on the same network segment.

## 3. Bring-up order

0. [ ] `docker compose ps -a` shows `pellmon-init` as `Exited (0)` before you check the daemon.
1. [ ] Start the daemon in the foreground so plugin errors are re-raised:
       `pellmonsrv debug` (add `-C /path/to/pellmon.conf` if needed).
   - [ ] Confirm the log shows `Activated plugins: ScotteCom` (or NBEcom) and no
         `Unable to execute the code in plugin` errors. Plugin load failures are logged
         at error level, and `pellmonsrv debug` re-raises them. Outside debug mode a
         plugin that fails to load just means no items, not a crash.
   - [ ] In debug mode, a plugin whose hardware library is missing (for example
         `raspberrygpio` without RPi) also aborts startup, so enable only the plugins you need.
2. [ ] Read-only first. Confirm items appear and compare several values with the
       burner display (temperatures, state, counters).
3. [ ] Compare raw frames with `scotte_protocol_spec.md`; capture serial traffic if you can.
4. [ ] Only when reads are correct: writes/commands, one at a time, attended.
       Re-read the value afterwards and check it on the burner display.
   - [ ] A rejected or unanswered write now raises an error (the web UI shows `error`
         and the log has a warning with the raw reply) instead of reporting OK. If you see
         `setItem ... rejected or unanswered`, the burner did not accept the value:
         re-read it on the burner display before retrying.
5. [ ] Confirm RRD updates are being written, then load a graph in the web UI
       (graph rendering was reworked to use an argument list and is untested with real rrdtool).
6. [ ] Web checks: login with the hashed password works, wrong password is rejected,
       config editor saves (same-origin check), UI is reachable only from the intended address.
7. [ ] Leave it running and watch the log for an extended period before trusting it.

### Home Assistant (supervised)

1. [ ] Dry run first with `tools/burner_sim.py` and a local mosquitto broker.
2. [ ] Stop the old publisher.
3. [ ] Enable the plugin and save on the Home Assistant page; confirm entities appear and history continues.
4. [ ] Unplug the burner serial link: entities go unavailable and return when reconnected.
5. [ ] Kill the pellmonsrv container: the last will marks the device "offline".
6. [ ] Enable commands, change one setpoint from Home Assistant while watching the burner display; confirm an out-of-range value snaps back.

## 4. Not verified

- [ ] Scotte/NBE protocol behaviour against real hardware (mock-verified only).
- [ ] Home Assistant/MQTT against a real broker, Home Assistant and burner (checklist above).
      Setpoint writes from Home Assistant are untested on hardware.
- [ ] Real D-Bus, rrdtool and serial/network I/O end to end.
- [ ] Docker Compose start-up end to end.
- [ ] Graph rendering with real rrdtool after the command-injection fix.
- [ ] Silent failure: about 50 broad `except:`/`pass` blocks in `pellmonsrv.py`, and many
      errors logged at `info`, can hide problems. Watch logs at the most verbose level
      and do not read silence as success.

## 5. Safety

- This controls a heating appliance. Do not test writes unattended.
- Know how to restore the original settings before changing anything.
- Do not commit files that identify your device (for example the `mqtt-*.json` export),
  and keep `config/pellmon.conf` and `.env` out of the repository.
