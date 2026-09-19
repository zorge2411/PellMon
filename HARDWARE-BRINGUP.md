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
- [ ] Back up the RRD database and the settings sqlite (keyval) database.
- [ ] Write down every setting currently on the burner, so you can restore it.
- [ ] Have the burner's own display/manual at hand as the reference for "correct" values.

## 2. Access to the burner

### Scotte (serial)

- [ ] Set `serialport` (e.g. `/dev/ttyUSB0`) and `chipversion` (`auto` or explicit)
      in `conf.d/plugins/scottecom.conf`.
      **If `serialport` is removed, the plugin runs on dummy data.** Values that look
      plausible are not proof you are talking to the burner.
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

1. [ ] Start the daemon in the foreground so plugin errors are re-raised:
       `pellmonsrv debug` (add `-C /path/to/pellmon.conf` if needed).
2. [ ] Read-only first. Confirm items appear and compare several values with the
       burner display (temperatures, state, counters).
3. [ ] Compare raw frames with `scotte_protocol_spec.md`; capture serial traffic if you can.
4. [ ] Only when reads are correct: writes/commands, one at a time, attended.
       Re-read the value afterwards and check it on the burner display.
5. [ ] Confirm RRD updates are being written, then load a graph in the web UI
       (graph rendering was reworked to use an argument list and is untested with real rrdtool).
6. [ ] Web checks: login with the hashed password works, wrong password is rejected,
       config editor saves (same-origin check), UI is reachable only from the intended address.
7. [ ] Leave it running and watch the log for an extended period before trusting it.

## 4. Not verified

- [ ] Scotte/NBE protocol behaviour against real hardware (mock-verified only).
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
