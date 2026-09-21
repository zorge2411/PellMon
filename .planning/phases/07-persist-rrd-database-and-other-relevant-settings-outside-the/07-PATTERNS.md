# Phase 7: Persist RRD database and settings outside the container - Pattern Map

**Mapped:** 2026-09-21
**Files analyzed:** 14
**Analogs found:** 12 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `docker-compose.yml` (bind mounts, `pellmon-init`, depends_on) | config | batch (one-shot init) | itself (`pellmonsrv`/`pellmonweb` blocks) | exact |
| `.env.example` | config | request-response | itself (SERIAL_GID block) | exact |
| `.gitignore`, `.dockerignore` | config | n/a | themselves | exact |
| `Dockerfile` | config | n/a | itself (likely no change, leave VOLUME/chown) | exact |
| `src/Pellmonsrv/pellmonsrv.py` (`check_data_dirs`, fallback fixes) | utility/startup | file-I/O | `run()` lines 933-948, `mkdir_p`, `copy_db` | role-match |
| `src/Pellmonweb/pellmonconf.py` (`save` read-only message) | controller | request-response | itself, `save()` lines 122-139 | exact |
| `src/Pellmonsrv/database.py` (`Keyval_storage` 0600) | model | CRUD | itself, lines 150-161 | exact |
| `tools/pellmon_backup.py` | utility (CLI) | batch / file-I/O | `tools/burner_sim.py` | role-match |
| `DEPLOY-PI.md`, `HARDWARE-BRINGUP.md` | docs | n/a | themselves | exact |
| `config/pellmon.conf.example` | config | n/a | itself | exact |
| `tests/test_ci_docker_config.py` (extend) | test | text check | itself | exact |
| `tests/Pellmonsrv/test_data_dir_check.py` (new) | test | file-I/O | `tests/Pellmonsrv/test_db_copy.py` | exact |
| `tests/Pellmonweb/test_pellmonconf_readonly.py` (new) | test | request-response | `tests/Pellmonweb/test_pellmonconf_path_traversal.py` | exact |
| `tests/test_backup_script.py` (new) | test | file-I/O | `tests/test_burner_sim_pty.py` (skip pattern) | partial |

## Pattern Assignments

### `docker-compose.yml` (config)

**Analog:** the existing file. Edit surgically; `tests/test_ci_docker_config.py::_service_block` splits services by two-space-indented `name:` keys, so the new `pellmon-init:` must use exactly two-space indent and the same style.

**Current mounts to replace** (lines 38-50 pellmonsrv, 101-113 pellmonweb):
```yaml
      - ./config/pellmon.conf:/etc/pellmon/pellmon.conf:ro
      - ./config/conf.d:/etc/pellmon/conf.d:ro
      # Data persistence (RRD database)
      - pellmon-data:/var/lib/pellmon
      # Logs
      - pellmon-logs:/var/log/pellmon
      - pellmon-run:/var/run/pellmon
```
Web: `pellmon-data:/var/lib/pellmon:ro` and `pellmon-logs:/var/log/pellmon`; conf.d currently `:ro` (must become writable for web only, D-08).

**depends_on form** (pellmonweb lines 82-84, copy for pellmonsrv -> init):
```yaml
    depends_on:
      pellmonsrv:
        condition: service_healthy
```
**Same-image/build pattern** (pellmonsrv lines 15-19; copy the `build:` block into `pellmon-init` to avoid pull race):
```yaml
    build:
      context: .
      dockerfile: Dockerfile
    image: pellmon:latest
```
**Interpolation convention** (lines 29, 32): `${SERIAL_GID:-20}`, `${TZ:-Europe/Stockholm}` -> use `${PELLMON_DATA_DIR:-./pellmon-data}/data:/var/lib/pellmon`.
**Command style** (lines 57-60): folded `>` with `sh -c "a && b"`.
Remove `pellmon-data` and `pellmon-logs` from the top-level `volumes:` (lines 132-138), keep `pellmon-run`. Use `restart: "no"` quoted. Do not use strings the regression tests forbid (`dbus-send --session --address`, `dbus-daemon --bus=`). Update header comment (lines 3-7) from `docker-compose` to `docker compose`.

---

### `.env.example` (config)

**Analog:** SERIAL_GID block (commented explanation, then `KEY=value`). The existing test `test_env_example_documents_serial_gid` uses `re.search(r"^SERIAL_GID=\d+\s*$", ..., re.M)`; mirror it for `PELLMON_DATA_DIR`:
```
# Group ID that owns your serial adapter ... 
SERIAL_GID=20
```
Add a commented explanation plus `PELLMON_DATA_DIR=./pellmon-data`, stating "use ./name or an absolute path" (a bare name would be a named volume).

### `.gitignore` / `.dockerignore`
`.gitignore` has sections with `# comment` headers and already `*.db`, `.env`; append `pellmon-data/` under a new comment. `.dockerignore` (untracked) is a plain list starting `# Ignore build artifacts`; append `pellmon-data/`.

---

### `src/Pellmonsrv/pellmonsrv.py` (startup check, data flow file-I/O)

**Insertion point:** `run()` lines 933-948, after `conf = config(config_file)` and before `commands[args.command]()`. Existing code:
```python
    if conf.polling:
        dbfile = conf.db
        dbdir = os.path.dirname(dbfile)
        mkdir_p(dbdir)
        logdir = os.path.dirname(conf.logfile)
        if args.USER:
            uid = pwd.getpwnam(args.USER).pw_uid
            ...
```
Add `check_data_dirs(conf)` here (module-level function next to `mkdir_p` at line 881). Message via both `sys.stderr.write` and `logger`, then `sys.exit(1)`. Follow project style: `%`-formatting, shared `logger`, `logger.warning`/`error` (not `info`).

**Fallbacks to fix in `config.__init__`** (lines 833-840):
```python
        try:
            self.keyval_db = parser.get('conf', 'settings_db')
        except:
            try:
                self.keyval_db = os.path.join(os.path.dirname(self.nvdb), 'pellmon_settings.db')
            except:
                self.keyval_db = '/tmp/pellmon_settings.db'
            mkdir_p(os.path.dirname(self.keyval_db))
```
Change `self.nvdb` to `self.db` (`self.nvdb` only set at line ~745 when polling). Other fallbacks: line 741 `self.db = '/tmp/pellmon_rrd_database.db'`; logfile fallback lines ~654-663 (`mkdir_p(logdir)` at 658 swallowed).

**Config-in-test pattern** (tests build a real `config` from a temp file): see `test_db_copy.py` lines 62-70.

---

### `src/Pellmonweb/pellmonconf.py` (`save`, request-response)

**Analog:** itself, lines 130-136:
```python
            try:
                path = self._resolve(filename)
                with codecs.open(path, 'w', 'utf-8') as f:
                    f.write(data)
                    return json.dumps({'success':True})
            except (ValueError, OSError) as e:
                return json.dumps({'success':False, 'error':str(e)})
```
Add a branch before the generic one: `except OSError as e: if e.errno in (errno.EROFS, errno.EACCES, errno.EPERM): return json.dumps({'success':False, 'error':'%s is read-only ...'})`. Add `import errno` to the import block (lines 20-38, stdlib style, one per line). Keep the `_check_same_origin` block (lines 125-129) and `_resolve` unchanged. Use `logger.warning` with `%r` args, as at line 126. Note the error value is a plain string (line 129 style), not a dict, except the "only POST" case.

---

### `src/Pellmonsrv/database.py` (`Keyval_storage`, CRUD)

**Analog:** itself, lines 150-161. Add `os.chmod(dbfile, 0o600)` after `conn.commit()` in try/except OSError (log `logger.warning`). Note `database.py` has no `logger` (CLAUDE.md), and has two `Keyval_storage` definitions (line 24 legacy and line 150; edit the one at 150, the effective later definition). Add `import os` if missing.

---

### `tools/pellmon_backup.py` (utility CLI, batch)

**Analog:** `tools/burner_sim.py`.

**Header** (lines 1-28): shebang, coding line, GPL docstring with `Copyright (C) 2013  Anders Nylund`, then a short description paragraph.
**Imports/logger** (lines 30-49): one stdlib import per line, `logger = logging.getLogger('burner_sim')` -> use `'pellmon_backup'`.
**CLI/main shape** (lines 423-465):
```python
def parse_args(argv=None):
    p = argparse.ArgumentParser(description='...')
    p.add_argument('--seed', type=int, default=None, help='...')
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format='%(asctime)s %(message)s')
    ...
    return 0

if __name__ == '__main__':
    sys.exit(main())
```
Return int from `main`, so tests call `main([...])`. Use `add_subparsers` for `backup`/`restore` (not in the analog; standard argparse). `%`-formatting and `sys.stderr.write` for errors. Stdlib only: `sqlite3.Connection.backup`, `tarfile`, `subprocess.run([...])` with argv lists (no shell). Effective RRD filename must come from config/manifest, not hard-coded (`rrd.db` vs `pellmon.rrd`). Archive mode 0600 via `os.open(..., 0o600)` or `os.chmod`.

---

### Tests

**`tests/test_ci_docker_config.py` (extend)** - reuse helpers and style:
```python
def _service_block(content, name):
    match = re.search(r"^  %s:\r?\n(.*?)(?=^  \S|^\S|\Z)" % re.escape(name), content, flags=re.M | re.S)
    assert match, "service %s not found in docker-compose.yml" % name
    return match.group(1)
```
Pattern for new test: `content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")`, `srv = _service_block(content, "pellmonsrv")`, then `assert` / `re.search` with message strings; docstring explains the regression. Add: `PELLMON_DATA_DIR` in srv/web/init blocks; web data mount ends `:ro`; `pellmon-run` still declared; `pellmon-data:`/`pellmon-logs:` absent; init has `user: root`, `restart: "no"`, `999:999`; srv has `condition: service_completed_successfully`; `.env.example` regex `^PELLMON_DATA_DIR=` (mirror line 153); `.gitignore`/`.dockerignore` contain `pellmon-data`. The existing "no tabs" loop (lines 77-79) is reusable.

**`tests/Pellmonsrv/test_data_dir_check.py` (new)** - use `daemon_module` fixture from `tests/Pellmonsrv/conftest.py` (stubs dbus/gi/pwd/grp off-Linux; imports `Pellmonsrv.pellmonsrv`). Patterns from `test_db_copy.py`:
```python
@pytest.fixture
def conf_stub(daemon_module):
    daemon_module.conf = SimpleNamespace(db="/tmp/a.db", nvdb="/tmp/b.db")
    yield daemon_module.conf
    del daemon_module.conf
```
```python
    conffile = tmp_path / "p.conf"
    conffile.write_text("[conf]\ndatabase = ...\n[pollvalues]\n...")
    c = daemon_module.config(str(conffile))
```
Use `SimpleNamespace(db=..., keyval_db=..., logfile=..., polling=True)` for `check_data_dirs`; `pytest.raises(SystemExit)`; `caplog.at_level("ERROR", logger="pellMon")` (lines 38-41). Skip permission cases with `pytest.mark.skipif(os.name == 'nt' or os.geteuid() == 0)`; guard `os.geteuid` on Windows. Config test for settings DB path deriving from `self.db` when polling off: build config from temp conf file with an invalid/absent pollvalues.

**`tests/Pellmonweb/test_pellmonconf_readonly.py` (new)** - copy the `inst` fixture and POST setup from `test_pellmonconf_path_traversal.py`:
```python
@pytest.fixture
def inst(tmp_path):
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\nconfig_dir=%s\n' % (tmp_path / 'conf.d'), encoding='utf-8')
    obj = Pellmonconf(config_file=str(conf), lookup=None)
    obj.dirs = {'pellmon.conf': str(tmp_path)}
    return obj

def test_save_allowed(inst, cherrypy_request_ctx, tmp_path):
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = {'Origin': 'http://localhost:8083', 'Host': 'localhost:8083'}
    r = json.loads(inst.save('pellmon.conf', 'hello'))
```
Portable read-only simulation: `mocker.patch('codecs.open', side_effect=OSError(errno.EROFS, 'Read-only file system'))` (same `mocker.patch('codecs.open')` style as line 29); assert `r['success'] is False` and `'read-only' in r['error']`. Uses `cherrypy_request_ctx` from `tests/conftest.py`.

**Keyval mode test** - add to `tests/Pellmonsrv/test_database.py` (style: `Keyval_storage(str(tmp_path / "test.db"))`, no fixtures); `stat.S_IMODE(os.stat(f).st_mode) == 0o600`, skip on Windows.

**`tests/test_backup_script.py` (new)** - import the tool via `importlib`/path (tools/ is not a package; see how `tests/test_burner_sim_pty.py` loads `tools/burner_sim.py` and skips without pty; reuse that loading and skip style, with `shutil.which('rrdtool')` for `pytest.mark.skipif`). Docker-mode argv test: monkeypatch `subprocess.run` and assert argv list.

## Shared Patterns

### Logging and errors
Shared `logger = getLogger('pellMon')` in daemon/web modules; `%`-formatting; use `warning`/`error` levels in new code; no bare `print` (`tests/test_no_ad_hoc_print.py` exists, so use `sys.stderr.write` or logger in `src/`; check it before adding output in `pellmonsrv.py`).

### GPL header
Copy the `burner_sim.py` lines 1-17 header block for new `.py` under `tools/`. Tests in this repo have no header (docstring only).

### Compose safety
Every compose edit must keep `tests/test_ci_docker_config.py` green (health check form, `dbus-daemon --session --address=`, `SERIAL_GID`, `XDG_CACHE_HOME=/tmp`, `start_period >= 60`).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `pellmon-init` compose service | init container | one-shot | No existing one-shot service; use the sketch in 07-RESEARCH.md ("Compose recommendation") |
| `tests/test_backup_script.py` docker-mode | test | subprocess mock | No existing subprocess-argv test of a CLI; closest is `test_rrd_command_injection.py` / `test_db_copy.py` argv-list assertions |

## Metadata

**Analog search scope:** `docker-compose.yml`, `.env.example`, `.gitignore`, `src/Pellmonsrv`, `src/Pellmonweb/pellmonconf.py`, `tools/`, `tests/`
**Files read:** ~11
**Pattern extraction date:** 2026-09-21
