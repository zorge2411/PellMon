"""D-16: change-listener hook on the daemon Database thread."""
import inspect
import logging


def _db(daemon_module):
    db = daemon_module.Database.__new__(daemon_module.Database)
    db.listeners = []
    db.values = {}
    return db


def test_listeners_called_once_with_params(daemon_module):
    db = _db(daemon_module)
    a, b = [], []
    db.add_change_listener(a.append)
    db.add_change_listener(b.append)
    params = [{'name': 'boiler_temp', 'value': '56'}]
    db._notify(params)
    assert a == [params]
    assert b == [params]


def test_failing_listener_does_not_stop_others(daemon_module, caplog):
    db = _db(daemon_module)
    seen = []

    def bad(params):
        raise RuntimeError('boom')

    db.add_change_listener(bad)
    db.add_change_listener(seen.append)
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        db._notify([{'name': 'x', 'value': '1'}])
    assert len(seen) == 1
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_snapshot_is_a_copy(daemon_module):
    db = _db(daemon_module)
    db.values = {'a': '1'}
    snap = db.snapshot()
    assert snap == db.values
    snap['b'] = '2'
    assert 'b' not in db.values


def test_listeners_defined_before_plugin_collection(daemon_module):
    src = inspect.getsource(daemon_module.Database.__init__)
    assert 'self.listeners = []' in src
    assert src.index('self.listeners = []') < src.index('collectPlugins')


def test_notify_inside_changed_block_not_under_dbus_service(daemon_module):
    lines = inspect.getsource(daemon_module.Database.run).splitlines()
    idx = [i for i, l in enumerate(lines) if 'self._notify(changed_params)' in l]
    assert len(idx) == 1
    notify_indent = len(lines[idx[0]]) - len(lines[idx[0]].lstrip())
    changed_i = next(i for i, l in enumerate(lines) if l.strip() == 'if changed_params:')
    changed_indent = len(lines[changed_i]) - len(lines[changed_i].lstrip())
    dbus_i = next(i for i, l in enumerate(lines) if l.strip() == 'if self.dbus_service:')
    dbus_indent = len(lines[dbus_i]) - len(lines[dbus_i].lstrip())
    assert idx[0] > changed_i
    assert notify_indent == changed_indent + 4
    assert notify_indent == dbus_indent
