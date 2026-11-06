"""Backup page controller (Phase 12): auth/CSRF guards, validation, actions, status mapping, template."""
import json
import logging
import re
import sys
import time
from pathlib import Path

import pytest
from mako.lookup import TemplateLookup

ORIGIN = dict(Origin='http://localhost:8081', Host='localhost:8081')

from Pellmonweb import backup as bp  # noqa: E402
from Pellmonsrv import backup_core as core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HTML_DIR = ROOT / 'src' / 'Pellmonweb' / 'html'

SETTINGS = dict(enabled=True, subfolder='', frequency='daily', time='03:00', weekday=6, keep_daily=14,
                keep_weekly=8, require_other_disk=True, available=True, root='/backups')
STATUS_OK = dict(available=True, state='ok', enabled=True, running=False, last_ok=1700000000.0, last_attempt=1700000000.0,
                 reason='', last_file='pellmon-backup-20231114-221320.tar.gz', last_size=3 * 1024 * 1024,
                 next_run=1700090000.0, root='/backups', folder='/backups', folder_exists=True, same_disk=False,
                 archive_count=1, archives=[dict(name='pellmon-backup-20231114-221320.tar.gz', size=3 * 1024 * 1024,
                                                 time=1700000000.0)])


NAME = 'pellmon-backup-20231114-221320.tar.gz'
PREVIEW_OK = {'ok': True, 'reason': '', 'name': NAME, 'size': 3 * 1024 * 1024, 'time': 1700000000.0,
              'manifest': {'created': '2023-11-14T22:13:20', 'machine': 'pi', 'rrdtool_version': '1.7.2',
                           'created_by': 'PellMon'}, 'has_config': True, 'restart': 'auto'}


class FakeTemplate:
    def __init__(self, sink):
        self.sink = sink

    def render(self, **kw):
        kw['_template'] = getattr(self, 'name', None)
        self.sink.append(kw)
        return kw


class FakeLookup:
    def __init__(self):
        self.calls = []

    def get_template(self, name):
        assert name in ('backup.html', 'backup_restore.html')
        t = FakeTemplate(self.calls)
        t.name = name
        return t


class FakeDbus:
    def __init__(self, fail=False, settings=None, status=None, set_result=None, start_result=None, test_result=None,
                 preview_result=None, restore_result=None, ack_fail=False):
        self.preview_result = PREVIEW_OK if preview_result is None else preview_result
        self.restore_result = {'ok': True, 'reason': ''} if restore_result is None else restore_result
        self.ack_fail = ack_fail
        self.fail = fail
        self.settings = dict(SETTINGS) if settings is None else settings
        self.status = dict(STATUS_OK) if status is None else status
        self.set_result = {'ok': True, 'errors': {}} if set_result is None else set_result
        self.start_result = {'ok': True, 'reason': ''} if start_result is None else start_result
        self.test_result = {'ok': True, 'reason': '', 'free_bytes': 5 * 1024 ** 3} if test_result is None else test_result
        self.calls = []

    def _check(self, name):
        self.calls.append(name)
        if self.fail:
            raise RuntimeError('down')

    def backup_get_settings(self):
        self._check('get')
        return dict(self.settings)

    def backup_set_settings(self, d):
        self._check('set')
        self.set_payload = d
        return self.set_result

    def backup_status(self):
        self._check('status')
        return self.status

    def backup_start(self):
        self._check('start')
        return self.start_result

    def backup_test(self):
        self._check('test')
        return self.test_result

    def backup_preview(self, name):
        self._check('preview')
        return self.preview_result

    def backup_restore(self, name):
        self._check('restore')
        self.restore_name = name
        return self.restore_result

    def backup_restore_ack(self):
        self.calls.append('ack')
        if self.ack_fail:
            raise RuntimeError('down')
        return {'ok': True}

    def wrote(self):
        return 'set' in self.calls or 'start' in self.calls or 'restore' in self.calls


def _make(creds=True, **kw):
    dbus = FakeDbus(**kw)
    return bp.Backup(FakeLookup(), dbus, credentials={'u': 'p'} if creds else {}), dbus


def _post(**headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)


def _valid(**kw):
    form = dict(enabled='1', subfolder='pellmon', frequency='weekly', time='04:30', weekday='2', keep_daily='10',
                keep_weekly='4', require_other_disk='1')
    form.update(kw)
    return form


def _redirect(fn, **form):
    import cherrypy
    with pytest.raises(cherrypy.HTTPRedirect) as exc:
        fn(**form)
    return exc.value


# ---- auth and CSRF ----

def test_auth_required_on_all_routes():
    for name in ('index', 'save', 'run', 'test', 'restore', 'restore_run', 'restore_status'):
        assert 'auth.require' in getattr(bp.Backup, name)._cp_config


@pytest.mark.parametrize('route', ['save', 'run', 'test'])
def test_get_is_rejected_without_dbus_write(cherrypy_request_ctx, route):
    import cherrypy
    cherrypy.request.method = 'GET'
    c, d = _make()
    ctx = getattr(c, route)()
    assert ctx['msg'] == bp.MSG_REJECTED and not d.wrote()


@pytest.mark.parametrize('route', ['save', 'run', 'test'])
def test_cross_origin_is_403(cherrypy_request_ctx, caplog, route):
    import cherrypy
    _post(Origin='http://evil.example', Host='localhost:8081')
    c, d = _make()
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        ctx = getattr(c, route)(**(_valid() if route == 'save' else {}))
    assert cherrypy.response.status == 403 and ctx['msg'] == bp.MSG_REJECTED
    assert not d.wrote() and 'test' not in d.calls
    assert any('evil.example' in r.getMessage() for r in caplog.records)


def test_headerless_post_rejected(cherrypy_request_ctx):
    _post(Host='localhost:8081')
    c, d = _make()
    c.run()
    assert not d.wrote()


def test_no_credentials_refuses_everything(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(creds=False)
    for route in (lambda: c.save(**_valid()), c.run, c.test):
        assert route()['msg'] == bp.MSG_AUTH_DISABLED
    assert not d.wrote() and 'test' not in d.calls


# ---- save ----

def test_valid_save_sends_clean_payload_and_redirects(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    r = _redirect(c.save, **_valid())
    assert d.set_payload == {'enabled': True, 'subfolder': 'pellmon', 'frequency': 'weekly', 'time': '04:30', 'weekday': 2,
                             'keep_daily': 10, 'keep_weekly': 4, 'require_other_disk': True}
    assert r.status == 303 and r.urls[0].endswith('/backup/?done=saved')


def test_unticked_checkboxes_mean_off(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    form = _valid()
    del form['enabled'], form['require_other_disk']
    r = _redirect(c.save, **form)
    assert d.set_payload['enabled'] is False and d.set_payload['require_other_disk'] is False
    assert r.urls[0].endswith('?done=off')


def test_invalid_input_never_reaches_the_daemon(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.save(**_valid(time='25:99', keep_daily='0', subfolder='../x'))
    assert set(ctx['errors']) == {'time', 'keep_daily', 'subfolder'}
    assert ctx['msg'] == bp.MSG_INVALID and 'set' not in d.calls
    assert ctx['settings']['time'] == '25:99'  # the user's input is shown again


def test_daemon_errors_are_shown(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(set_result={'ok': False, 'errors': {'time': 'Enter the time as HH:MM, for example 03:00.'}})
    ctx = c.save(**_valid())
    assert ctx['errors'] == {'time': 'Enter the time as HH:MM, for example 03:00.'} and ctx['msg'] == bp.MSG_INVALID


def test_plugin_not_active_and_daemon_down_on_save(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(set_result={'ok': False, 'available': False, 'errors': {}})
    assert c.save(**_valid())['msg'] == bp.MSG_NOT_ACTIVE
    c, d = _make(fail=True)
    ctx = c.save(**_valid())
    assert ctx['msg'] == bp.MSG_DAEMON_DOWN and ctx['msg_level'] == 'danger'


# ---- run and test ----

def test_run_started(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    r = _redirect(c.run)
    assert r.urls[0].endswith('/backup/?done=started') and 'start' in d.calls


def test_run_busy_and_failed(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(start_result={'ok': False, 'reason': 'a backup is already running'})
    assert _redirect(c.run).urls[0].endswith('?done=busy')
    c, d = _make(start_result={'ok': False, 'reason': 'something else'})
    assert _redirect(c.run).urls[0].endswith('?done=failed')


def test_run_not_active_and_daemon_down(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(start_result={'ok': False, 'available': False, 'reason': ''})
    assert c.run()['msg'] == bp.MSG_NOT_ACTIVE
    c, d = _make(fail=True)
    assert c.run()['msg'] == bp.MSG_DAEMON_DOWN


def test_folder_test_ok_shows_free_space(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.test()
    assert ctx['msg'] == bp.MSG_TEST_OK_FREE % '5.0 GB' and ctx['msg_level'] == 'success'


def test_folder_test_failure_shows_a_known_reason_only(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(test_result={'ok': False, 'reason': core.REASON_FOLDER_MISSING, 'free_bytes': None})
    ctx = c.test()
    assert ctx['msg'] == bp.MSG_TEST_FAILED % core.REASON_FOLDER_MISSING and ctx['msg_level'] == 'danger'
    c, d = _make(test_result={'ok': False, 'reason': '/secret/path: permission denied', 'free_bytes': None})
    assert '/secret' not in c.test()['msg']


# ---- index and messages ----

@pytest.mark.parametrize('done,level', [('saved', 'success'), ('off', 'success'), ('started', 'success'),
                                        ('busy', 'warning'), ('failed', 'danger'), ('restoring', 'success'),
                                        ('restore_busy', 'warning'), ('restore_backup_busy', 'warning')])
def test_index_done_messages(cherrypy_request_ctx, done, level):
    c, d = _make()
    ctx = c.index(done=done)
    assert ctx['msg'] == bp.DONE_MESSAGES[done][0] and ctx['msg_level'] == level


def test_index_ignores_unknown_done_codes(cherrypy_request_ctx):
    c, d = _make()
    assert c.index(done='<script>')['msg'] == ''


def test_index_daemon_down(cherrypy_request_ctx):
    c, d = _make(fail=True)
    ctx = c.index()
    assert ctx['msg'] == bp.MSG_DAEMON_DOWN and ctx['daemon_down'] is True and ctx['status']['level'] == 'warning'


def test_context_for_the_template(cherrypy_request_ctx):
    c, d = _make()
    ctx = c.index()
    assert ctx['active_page'] == 'backup' and ctx['root'] == '/backups' and ctx['archive_count'] == 1
    assert ctx['archives'][0]['size'] == '3.0 MB' and ctx['weekdays'][0] == 'Monday'


# ---- status mapping ----

def test_status_views():
    ok = bp.status_view(STATUS_OK)
    assert ok['level'] == 'success' and 'Next backup' in ok['text'] and '3.0 MB' in ok['text']
    assert bp.status_view(dict(STATUS_OK, enabled=False))['text'].find('Next backup') == -1
    err = bp.status_view(dict(STATUS_OK, state='error', reason=core.REASON_NO_SPACE))
    assert err['level'] == 'danger' and core.REASON_NO_SPACE in err['text'] and 'retries every hour' in err['text']
    assert 'retries' not in bp.status_view(dict(STATUS_OK, state='error', enabled=False, reason=core.REASON_RRD))['text']
    assert core.REASON_UNKNOWN in bp.status_view(dict(STATUS_OK, state='error', reason='/etc/shadow leaked'))['text']
    assert 'leaked' not in bp.status_view(dict(STATUS_OK, state='error', reason='/etc/shadow leaked'))['text']
    assert bp.status_view(dict(STATUS_OK, state='running'))['word'] == 'Running.'
    assert bp.status_view(dict(STATUS_OK, state='disabled', enabled=False))['word'] == 'Off.'
    assert bp.status_view(dict(STATUS_OK, state='waiting'))['word'] == 'Waiting.'
    assert 'not active' in bp.status_view({'available': False})['text']
    assert 'not running' in bp.status_view(None, daemon_down=True)['text']


def test_warnings():
    assert bp.warnings({}, STATUS_OK) == []
    assert bp.warnings({}, dict(STATUS_OK, same_disk=True)) == [bp.WARN_SAME_DISK]
    assert bp.warnings({}, dict(STATUS_OK, folder_exists=False)) == [bp.WARN_NO_FOLDER]
    assert bp.warnings({}, {'available': False}) == [] and bp.warnings({}, None) == []


def test_human_size():
    assert [bp.human_size(n) for n in (0, 1023, 1024, 1536, 3 * 1024 ** 2, 5 * 1024 ** 3, None, 'x')] == \
        ['0 B', '1023 B', '1.0 kB', '1.5 kB', '3.0 MB', '5.0 GB', '', '']


# ---- template ----

def render(**over):
    settings = dict(SETTINGS)
    settings.update(over.pop('settings', {}))
    ctx = dict(username='u', webroot='', active_page='backup', settings=settings, weekdays=bp.WEEKDAYS, errors={}, msg='',
               msg_level='', auth_configured=True, available=True, daemon_down=False, root='/backups',
               status=bp.status_view(STATUS_OK), warnings=[], archives=bp.archive_rows(STATUS_OK), archive_count=1,
               folder='/backups/pellmon', restore=bp.restore_view(STATUS_OK))
    ctx.update(over)
    return TemplateLookup(directories=[str(HTML_DIR)]).get_template('backup.html').render(**ctx)


def _tag(html, name):
    for t in re.findall(r'<(?:input|select)\b[^>]*>', html):
        if 'name="%s"' % name in t:
            return t
    return None


def test_template_has_every_form_field_and_the_three_forms():
    html = render()
    for name in ('enabled', 'frequency', 'time', 'weekday', 'keep_daily', 'keep_weekly', 'subfolder', 'require_other_disk'):
        assert _tag(html, name), name
    assert html.count('<form') == 3
    for action in ('/backup/save', '/backup/run', '/backup/test'):
        assert 'action="%s"' % action in html
    assert 'checked' in _tag(html, 'enabled') and 'checked' in _tag(html, 'require_other_disk')
    assert html.count('<option') == 9
    assert 'selected' in re.search(r'<option value="6"[^>]*>', html).group(0)


def test_template_shows_status_archives_and_active_menu_entry():
    html = render()
    assert 'pellmon-backup-20231114-221320.tar.gz' in html and '3.0 MB' in html
    assert 'Last backup' in html and 'class="active"' in html
    assert re.search(r'class="active">\s*<a href="/backup/">Backup</a>', html)


def test_template_escapes_user_text():
    html = render(settings={'subfolder': '"><script>alert(1)</script>'}, msg='<b>x</b>', msg_level='danger',
                  errors={'subfolder': '<i>bad</i>'})
    assert '<script>alert(1)</script>' not in html and '<b>x</b>' not in html and '<i>bad</i>' not in html


def test_template_disables_buttons_without_credentials_or_plugin():
    def disabled(html):
        return len(re.findall(r'<button[^>]* disabled>', html))
    assert disabled(render()) == 0
    assert disabled(render(auth_configured=False)) == 3
    assert disabled(render(available=False)) == 2


def test_template_empty_state_and_warnings():
    html = render(archives=[], archive_count=0, warnings=[bp.WARN_SAME_DISK])
    assert 'No backups in this folder yet' in html and 'same disk as the database' in html
    assert 'Showing the newest' not in render(archive_count=30)


def test_menu_entry_exists_in_layout():
    assert '/backup/' in (HTML_DIR / 'layout.html').read_text(encoding='utf-8')


def test_slow_folder_warning():
    assert bp.warnings({}, dict(STATUS_OK, folder_slow=True)) == [bp.WARN_SLOW]
    assert bp.warnings({}, dict(STATUS_OK, folder_slow=True, same_disk=True)) == [bp.WARN_SLOW]


def test_timeout_reason_is_shown_as_is(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(test_result={'ok': False, 'reason': core.REASON_TIMEOUT, 'free_bytes': None})
    assert c.test()['msg'] == bp.MSG_TEST_FAILED % core.REASON_TIMEOUT


# ---- restore (Phase 13) ----

def _status_restore(**block):
    st = dict(STATUS_OK)
    st['restore'] = block
    return st


def test_restore_get_has_no_side_effects(cherrypy_request_ctx):
    c, d = _make()
    ctx = c.restore(name=NAME)
    assert ctx['_template'] == 'backup_restore.html' and ctx['name'] == NAME
    assert ctx['size'] == '3.0 MB' and ctx['machine'] == 'pi' and ctx['rrdtool_version'] == '1.7.2'
    assert ctx['has_config'] is True and ctx['restart'] == 'auto' and ctx['when']
    assert 'restore' not in d.calls and 'preview' in d.calls and not d.wrote()


@pytest.mark.parametrize('name', ['', '../x', 'a/' + NAME, 'x.tar.gz', ['a', 'b'], None])
def test_restore_bad_names(cherrypy_request_ctx, name):
    c, d = _make()
    ctx = c.restore(name=name)
    assert ctx['msg'] == bp.MSG_RESTORE_NOT_FOUND and 'preview' not in d.calls


def test_restore_preview_failures(cherrypy_request_ctx):
    c, d = _make(fail=True)
    assert c.restore(name=NAME)['msg'] == bp.MSG_DAEMON_DOWN
    c, d = _make(preview_result={'available': False})
    assert c.restore(name=NAME)['msg'] == bp.MSG_NOT_ACTIVE
    c, d = _make(preview_result={'ok': False, 'reason': '/secret/path'})
    msg = c.restore(name=NAME)['msg']
    assert core.REASON_UNKNOWN in msg and '/secret' not in msg
    c, d = _make(preview_result={'ok': False, 'reason': core.REASON_TIMEOUT})
    assert core.REASON_TIMEOUT in c.restore(name=NAME)['msg']


def test_restore_run_guards(cherrypy_request_ctx, caplog):
    import cherrypy
    cherrypy.request.method = 'GET'
    c, d = _make()
    assert c.restore_run(name=NAME, confirm='RESTORE')['msg'] == bp.MSG_REJECTED
    _post(Origin='http://evil.example', Host='localhost:8081')
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        c.restore_run(name=NAME, confirm='RESTORE')
    assert cherrypy.response.status == 403
    assert any('evil.example' in r.getMessage() for r in caplog.records)
    _post(**ORIGIN)
    c2, d2 = _make(creds=False)
    assert c2.restore_run(name=NAME, confirm='RESTORE')['msg'] == bp.MSG_AUTH_DISABLED
    assert 'restore' not in d.calls and 'restore' not in d2.calls


@pytest.mark.parametrize('word', ['', 'restore', 'RESTOR'])
def test_restore_run_confirm_word(cherrypy_request_ctx, word):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.restore_run(name=NAME, confirm=word)
    assert 'restore' not in d.calls
    assert ctx['_template'] == 'backup_restore.html' and ctx['error'] == bp.MSG_CONFIRM_WORD


def test_restore_run_confirm_word_whitespace_accepted(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    r = _redirect(c.restore_run, name=NAME, confirm=' RESTORE ')
    assert 'restore' in d.calls and d.restore_name == NAME and r.status == 303


def test_restore_run_started(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    assert _redirect(c.restore_run, name=NAME, confirm='RESTORE').urls[0].endswith('/backup/?done=restoring')
    c, d = _make(restore_result={'ok': False, 'reason': core.REASON_RESTORE_BUSY})
    assert _redirect(c.restore_run, name=NAME, confirm='RESTORE').urls[0].endswith('?done=restore_busy')
    c, d = _make(restore_result={'ok': False, 'reason': bp.BACKUP_BUSY_REASON})
    assert _redirect(c.restore_run, name=NAME, confirm='RESTORE').urls[0].endswith('?done=restore_backup_busy')
    c, d = _make(restore_result={'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND})
    assert core.REASON_ARCHIVE_NOT_FOUND in c.restore_run(name=NAME, confirm='RESTORE')['msg']
    c, d = _make(fail=True)
    assert c.restore_run(name=NAME, confirm='RESTORE')['msg'] == bp.MSG_DAEMON_DOWN
    c, d = _make(restore_result={'available': False})
    assert c.restore_run(name=NAME, confirm='RESTORE')['msg'] == bp.MSG_NOT_ACTIVE


def test_backup_busy_reason_matches_plugin():
    from Pellmonsrv.plugins import backup as plugin
    assert bp.BACKUP_BUSY_REASON == plugin.REASON_BUSY


def test_run_during_restore(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(start_result={'ok': False, 'reason': core.REASON_RESTORE_BUSY})
    assert _redirect(c.run).urls[0].endswith('?done=restore_busy')


def test_restore_status_json(cherrypy_request_ctx):
    import cherrypy
    c, d = _make(status=_status_restore(state='idle', step=0, steps=5, name='', reason='', restart='auto', result=None))
    out = json.loads(c.restore_status())
    assert cherrypy.response.headers['Content-Type'] == 'application/json' and out['active'] is False
    for n, step in enumerate(bp.STEP_TEXT, 1):
        c, d = _make(status=_status_restore(state=step, step=n, steps=5, name=NAME, reason='', restart='auto', result=None))
        out = json.loads(c.restore_status())
        assert out['active'] is True and 'step %d of 5' % n in out['text']
    c, d = _make(fail=True)
    out = json.loads(c.restore_status())
    assert out['state'] == 'daemon_down' and out['active'] is True and out['text'].startswith('Restarting the server')
    res = dict(name=NAME, time=1700000000.0, ok=True, reason='', restart='auto', acknowledged=False)
    c, d = _make(status=_status_restore(state='done', step=5, steps=5, name=NAME, reason='', restart='auto', result=res))
    out = json.loads(c.restore_status())
    assert out['level'] == 'success' and NAME in out['text'] and out['active'] is False
    c, d = _make(status=_status_restore(state='failed', step=3, steps=5, name=NAME, reason='/etc/passwd', restart='auto', result=None))
    out = json.loads(c.restore_status())
    assert core.REASON_UNKNOWN in out['text'] and '/etc' not in json.dumps(out) and out['level'] == 'danger'


def test_restore_view_manual_restart():
    v = bp.restore_view(_status_restore(state='done', step=5, steps=5, name=NAME, reason='', restart='manual', result=None))
    assert 'Restart the PellMon server now' in v['text'] and v['level'] == 'warning'


def test_index_shows_result_once(cherrypy_request_ctx):
    res = dict(name=NAME, time=1700000000.0, ok=True, reason='', restart='auto', acknowledged=False)
    st = _status_restore(state='done', step=5, steps=5, name=NAME, reason='', restart='auto', result=res)
    c, d = _make(status=st)
    ctx = c.index()
    assert ctx['restore']['level'] == 'success' and 'ack' in d.calls
    c, d = _make(status=st, ack_fail=True)
    assert c.index()['restore']['level'] == 'success'
    c, d = _make()
    c.index()
    assert 'ack' not in d.calls


def render_confirm(**over):
    ctx = dict(username='u', webroot='', active_page='backup', name=NAME, when='2023-11-14 22:13', size='3.0 MB',
               created='2023-11-14T22:13:20', machine='pi', rrdtool_version='1.7.2', created_by='PellMon',
               has_config=False, restart='auto', auth_configured=True, error='')
    ctx.update(over)
    return TemplateLookup(directories=[str(HTML_DIR)]).get_template('backup_restore.html').render(**ctx)


def test_template_restore_links():
    html = render()
    m = re.search(r'<a [^>]*href="/backup/restore\?name=([^"]+)"[^>]*>Restore\.\.\.</a>', html)
    assert m and m.group(1) == NAME
    assert html.count('<form') == 3
    for kw in (dict(auth_configured=False), dict(available=False)):
        h = render(**kw)
        assert 'backup/restore?name=' not in h and 'text-muted">Restore...' in h


def test_template_restore_panel():
    html = render()
    tag = re.search(r'<div id="backup-restore"[^>]*>', html).group(0)
    assert 'data-url="/backup/restore_status"' in tag and 'data-active="0"' in tag
    assert 'role="status"' in tag and 'aria-live="polite"' in tag
    busy = bp.restore_view(dict(STATUS_OK, restore=dict(state='extracting', step=2, steps=5, name=NAME)))
    html = render(restore=dict(busy, text='<b>x</b>'))
    assert 'data-active="1"' in html and '<b>x</b>' not in html and '&lt;b&gt;x&lt;/b&gt;' in html


def test_template_help_mentions_with_config():
    html = render()
    assert 'pellmon_backup.py restore --with-config' in html and 'Showing the newest' not in html


def test_confirm_template():
    html = render_confirm(machine='<script>x</script>', has_config=True)
    assert '<script>x</script>' not in html and '&lt;script&gt;' in html
    assert html.count('<form') == 1 and 'method="post"' in html and 'action="/backup/restore_run"' in html
    assert re.search(r'<input type="hidden" name="name" value="%s"' % re.escape(NAME), html)
    assert re.search(r'<input[^>]*name="confirm"[^>]*autocomplete="off"', html)
    for text in ('.pre-restore', 'after the backup was made is lost', 'not restored', '--with-config',
                 'restarts by itself', '2023-11-14 22:13', '1.7.2'):
        assert text in html, text
    assert 'href="/backup/"' in html and 'disabled' not in html
    assert 'Restart the PellMon server when the restore is done' in render_confirm(restart='manual')
    assert 'contains configuration files' not in render_confirm(has_config=False)
    assert re.search(r'<button[^>]* disabled>', render_confirm(auth_configured=False))
