---
status: resolved
trigger: "webpage does not load after doing Phase 8 checklist step 7 (docker compose stop pellmonsrv, then start pellmonsrv) -- pellmonweb main page returns 500, traceback ends in DbusNotConnected: server not running, despite pellmonsrv container showing healthy in docker ps"
created: 2026-09-23T12:14:33Z
updated: 2026-09-23T14:52:00Z
---

## Human Verification (2026-09-23)

Confirmed fixed on the real Pi after deploying PR #20 (v2.0.4) and doing a full
`docker compose stop && docker compose up -d`, then repeating the step 7 test
(`docker compose stop pellmonsrv` / `start pellmonsrv`) with all three services
(`pellmon-dbus`, `pellmonsrv`, `pellmonweb`) healthy beforehand:

- `docker logs pellmonweb` shows `GET / HTTP/1.1" 200` twice shortly after pellmonsrv
  came back up -- the main page recovered on its own via pellmonweb's existing
  watch_name_owner reconnect logic, exactly as the fix intended. No manual pellmonweb
  restart was needed for THIS specific failure mode.
- A separate, unrelated crash occurred moments later (a WebSocket upgrade request hit
  a race against D-Bus not being ready yet, then an unhandled cheroot exception took
  the whole HTTP server down). That is a distinct bug -- see
  `.planning/debug/pellmonweb-cheroot-crash-no-restart.md`. It does NOT reopen this
  session; the D-Bus-daemon-lifecycle root cause this session investigated is fixed
  and confirmed.

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

hypothesis: CONFIRMED (see Resolution). Root cause is architectural, not a code-level watcher bug: dbus-daemon itself is started inside pellmonsrv's container command (`dbus-daemon --session --address=.../bus_socket --fork && exec python3 -m Pellmonsrv...`), so every `docker compose stop/start pellmonsrv` kills and recreates the ENTIRE bus daemon process, not just the org.pellmon.int service on a stable bus. pellmonweb's Dbus_handler.start() calls `Dbus.SessionBus()` exactly once at process startup (pellmonweb.py:176, invoked once from pellmonweb.py:1080) and never reconnects that DBusConnection object. Its `watch_name_owner` callback (pellmonweb.py:159-169) only handles the case where org.pellmon.int appears/disappears on the SAME live bus connection -- it cannot recover when the whole dbus-daemon process (and therefore the underlying socket peer) is replaced, because the old DBusConnection is permanently dead and no new connection is ever attempted.
test: Reviewed Dbus_handler class in full and docker-compose.yml's pellmonsrv command directive.
expecting: n/a -- confirmed via direct code/config read, not runtime test (no shell access to the Pi).
next_action: Implement fix -- decouple the dbus-daemon process into its own docker-compose service with an independent lifecycle so restarting pellmonsrv (or pellmonweb) never kills/recreates the shared bus. Then hand back an explicit manual verification step to the user (rebuild/redeploy on the Pi, repeat checklist step 7, confirm page self-heals without restarting pellmonweb).
reasoning_checkpoint:
  hypothesis: "pellmonweb never recovers after `docker compose stop/start pellmonsrv` because the D-Bus session bus daemon itself lives inside the pellmonsrv container's startup command and is killed/recreated on every pellmonsrv restart, while pellmonweb holds one long-lived DBusConnection object (created once in Dbus_handler.start()) that is never re-established -- its name-owner watcher only detects service (dis)appearance on a live bus, not bus-daemon replacement."
  confirming_evidence:
    - "docker-compose.yml pellmonsrv command: `rm -f bus_socket && dbus-daemon --session --address=unix:path=/var/run/pellmon/bus_socket --fork && exec python3 -m Pellmonsrv.pellmonsrv ...` -- a fresh dbus-daemon process (and thus a new socket peer) is spawned every container start, tied to pellmonsrv's lifecycle."
    - "pellmonweb.py:176 `self.bustype = Dbus.SessionBus()` is called exactly once, from Dbus_handler.start() at pellmonweb.py:1080 (single call site, process startup only) -- no reconnect path exists anywhere in the file (grep for SessionBus(/reconnect found only this one call)."
    - "docker ps evidence already in Evidence section: pellmonweb container uptime predates pellmonsrv's current uptime, proving pellmonweb's process (and its one DBusConnection) survived the whole stop/start cycle unchanged."
  falsification_test: "If dbus-daemon were instead a separate, independently-lived process/service (not restarted when pellmonsrv restarts), pellmonweb's existing watch_name_owner callback would correctly detect org.pellmon.int leaving and returning on the SAME bus connection, and remote_object would be reset automatically -- this would disprove the hypothesis. Since the compose file demonstrates dbus-daemon is in fact restarted with pellmonsrv, the hypothesis holds."
  fix_rationale: "Fixing pellmonweb's Python reconnect logic alone would be treating the symptom (no reconnect-on-broken-connection handling) while leaving the actual architectural defect (bus daemon coupled to one service's container lifecycle) in place -- any other transient pellmonsrv restart would reproduce this. The correct root-cause fix is infrastructural: give the D-Bus daemon its own compose service with `restart: unless-stopped` independent of both pellmonsrv and pellmonweb, so the bus (and thus pellmonweb's single long-lived connection to it) survives restarts of either consuming service."
  blind_spots: "Cannot verify on the real Pi (no shell/docker access this session) that the new pellmon-dbus service actually keeps the bus alive across a pellmonsrv restart, or that dbus-daemon runs correctly as a non-forking foreground process under the pellmon (non-root) user in a plain (non-privileged) container. Also have not verified whether pellmonsrv's `privileged: true` requirement was only for D-Bus (now moot) or also serial/device access (still needed) -- assumed the latter and left it in place for pellmonsrv only."
tdd_checkpoint: null

## Symptoms
<!-- Written during gathering, then immutable -->

expected: After `docker compose stop pellmonsrv` then `docker compose start pellmonsrv` (Phase 8 checklist step 7), the main pellmonweb page should recover automatically once pellmonsrv is back up and reachable over D-Bus -- CLAUDE.md documents Dbus_handler as "watches name owner" specifically for this purpose.
actual: Main page (`GET /`) returns HTTP 500 indefinitely after pellmonsrv restarts. `docker ps` shows pellmonsrv container healthy and "Up 4 minutes", pellmonweb container unhealthy and "Up 5 minutes" (i.e. pellmonweb has been running continuously since BEFORE pellmonsrv's restart and never recovered).
errors: |
  Nested traceback (full text in conversation, user-pasted docker logs pellmonweb):
  1. mako.lookup.TopLevelLookupException: Can't locate template for uri 'consumption24h'
     (thrown by mako trying to resolve the widget URI 'consumption24h' as a template file)
  2. During handling of #1, myLookup.get_template() falls back to
     `self.dbus.getPlugins(uri)` to look up a plugin-provided template --
     this raises AttributeError: 'NoneType' object has no attribute 'getPlugins'
     (pellmonweb.py:246, self.remote_object is None)
  3. Dbus_handler.getPlugins's bare except re-raises as
     DbusNotConnected("server not running") (pellmonweb.py:248)
  4. Uncaught DbusNotConnected propagates out of cherrypy's index() handler
     (pellmonweb.py:700, tmpl.render(...)) -> HTTP 500, no graceful fallback page.
  Two independent things are tangled together here and need to be separated:
  (a) 'consumption24h' is not a real bundled template name (default frontpage_widgets
      config uses 'consumption7d', not 'consumption24h' -- possibly a user config typo,
      OR a real widget name that's supposed to be plugin-provided and normally resolves
      fine when pellmonsrv/D-Bus IS connected). Needs checking against the
      `consumption` plugin's actual provided widget/template names.
  (b) Even if (a) is a legitimate plugin-provided widget name, the get_template()
      fallback to query the daemon for it should not raise an unhandled 500 when the
      daemon is unreachable -- some other main-page widget/path already has a documented
      graceful "daemon down" degraded render (per DEPLOY-PI.md's daemon-down expectations
      exercised in Phase 8 step 7's OWN acceptance criteria: "main page still renders ...
      no error page" -- that expectation was written for the *systemimage* endpoint
      specifically, not necessarily for arbitrary widget template lookups, so this may be
      a real, previously-unexercised gap).
reproduction: |
  1. Have pellmonweb's frontpage_widgets config include a widget whose template lookup
     depends on pellmonsrv being reachable (confirmed trigger: happened during Phase 8
     checklist step 7, i.e. right after `docker compose stop pellmonsrv` then
     `docker compose start pellmonsrv`).
  2. GET / on pellmonweb after pellmonsrv restarts -- 500, does not self-heal.
  3. Per `docker ps`: pellmonsrv container is healthy and running; pellmonweb container
     is unhealthy and has an EARLIER start time than pellmonsrv (confirms pellmonweb
     was alive through the whole stop/start cycle and never recovered its connection).
started: Today (2026-09-23), during live Phase 8 Task 4 checklist step 7 verification on
  the real Pi deployment (right after the systemimage bugs from v2.0.2/v2.0.3 were fixed
  and confirmed working).

## Eliminated
<!-- APPEND only - prevents re-investigating after /clear -->

## Evidence
<!-- APPEND only - facts discovered during investigation -->

- timestamp: 2026-09-23T12:14:33Z
  checked: docker ps output on the real Pi (user-provided screenshot)
  found: pellmonsrv container healthy, Up 4 minutes. pellmonweb container unhealthy, Up 5 minutes (longer than pellmonsrv -- pellmonweb predates pellmonsrv's current uptime).
  implication: pellmonweb was running continuously across pellmonsrv's stop+restart and never recovered its D-Bus connection to it -- rules out "pellmonsrv is still stopped" as the explanation; this is a reconnect/recovery bug in pellmonweb's own D-Bus client, not a leftover-stopped-daemon issue.

- timestamp: 2026-09-23T12:20:00Z
  checked: src/Pellmonweb/pellmonweb.py Dbus_handler class in full (lines 151-249) and its single call site
  found: Dbus_handler.start() creates one Dbus.SessionBus() connection (line 176), calls watch_name_owner once, and registers owner_changed which DOES correctly reset self.remote_object to None/re-fetch it when org.pellmon.int's owner changes on that SAME connection. Dbus_handler.start() itself is only ever invoked once, from pellmonweb.py:1080 at process startup. Grep across the file for SessionBus(/reconnect found no other call sites.
  implication: The name-owner watcher logic is not itself buggy -- it correctly handles the "org.pellmon.int process restarts, dbus-daemon stays up" case. The bug is that this assumption (stable dbus-daemon) doesn't hold in this deployment.

- timestamp: 2026-09-23T12:24:00Z
  checked: docker-compose.yml pellmonsrv service `command:` directive
  found: "rm -f /var/run/pellmon/bus_socket && dbus-daemon --session --address=unix:path=/var/run/pellmon/bus_socket --fork && exec python3 -m Pellmonsrv.pellmonsrv ..." -- dbus-daemon is started fresh, as a NEW process, every time the pellmonsrv container starts.
  implication: Root cause confirmed -- restarting pellmonsrv doesn't just restart org.pellmon.int on a stable bus, it destroys and recreates the entire bus daemon/socket peer. pellmonweb's one-shot SessionBus() connection from the previous bus instance is permanently dead with no code path to reconnect.

- timestamp: 2026-09-23T12:28:00Z
  checked: DEPLOY-PI.md backup/restore section (line 264-265, pre-fix wording)
  found: Pre-existing documented caveat: "After a restore the daemon restarts on a new D-Bus socket, so also run `docker compose restart pellmonweb` (the web page shows 'server not running' until you do)." -- this is the SAME bug, already known and worked around manually for the restore path (which also restarts pellmonsrv's container), just never connected to the Phase 8 checklist step 7 scenario.
  implication: Strong corroborating evidence for the root cause -- independent confirmation that any pellmonsrv container restart (not just the checklist's manual stop/start) strands pellmonweb's D-Bus connection, consistent with a bus-daemon lifecycle bug rather than something specific to the checklist's exact commands.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: pellmonweb never recovers its D-Bus connection after `docker compose stop pellmonsrv` + `start pellmonsrv` because the D-Bus session bus daemon itself is spawned inline inside pellmonsrv's container command (docker-compose.yml `command:` for the pellmonsrv service) and is therefore killed and recreated as a brand-new process/socket-peer every time pellmonsrv's container restarts. pellmonweb's Dbus_handler establishes exactly one Dbus.SessionBus() connection at process startup (pellmonweb.py Dbus_handler.start(), single call site) and never re-establishes it; its watch_name_owner callback only detects org.pellmon.int appearing/disappearing on a live bus connection, not the replacement of the bus daemon itself, so once the old dbus-daemon dies the connection is permanently dead with no recovery path short of restarting the pellmonweb process.
fix: Decouple the D-Bus daemon into its own docker-compose service (pellmon-dbus) with an independent restart policy, so it is not restarted when pellmonsrv or pellmonweb restart. pellmonsrv no longer starts dbus-daemon itself -- it just connects to the now-stable shared socket. This preserves the existing bus connection across pellmonsrv restarts, so pellmonweb's existing (correct, previously-untested-in-this-scenario) watch_name_owner reconnect logic works as originally designed.
verification: Self-verified structurally (docker-compose.yml service graph, command directives, healthchecks) -- cannot runtime-verify on the real Pi this session (no shell/docker access). Requires explicit manual verification from the user: rebuild+redeploy stack on the Pi, repeat Phase 8 checklist step 7 (stop/start pellmonsrv only, not pellmon-dbus), confirm pellmonweb's main page self-heals without needing a pellmonweb restart.
files_changed:
  - docker-compose.yml
