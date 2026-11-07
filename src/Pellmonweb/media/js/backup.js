/* Backup page: follows a running restore through the server restart.
   Only textContent and className are written (no HTML sinks). */
(function () {
    'use strict';
    var INTERVAL_MS = 2000;
    var GIVE_UP_MS = 30 * 60 * 1000;
    var RESTARTING = 'Restarting the server... This page reconnects by itself.';
    var GAVE_UP = 'The server did not come back. Check it on the host with docker compose ps.';
    var LEVELS = ['success', 'info', 'warning', 'danger'];

    var el = document.getElementById('backup-restore');
    if (!el || el.getAttribute('data-active') !== '1') {
        return;
    }
    var url = el.getAttribute('data-url');
    if (!url) {
        return;
    }
    var started = new Date().getTime();
    var timer = null;

    function show(text, level) {
        el.textContent = String(text || '');
        el.className = LEVELS.indexOf(level) >= 0 ? 'alert alert-' + level : 'well';
    }

    function schedule() {
        timer = window.setTimeout(poll, INTERVAL_MS);
    }

    function poll() {
        if (new Date().getTime() - started > GIVE_UP_MS) {
            show(GAVE_UP, 'danger');
            return;
        }
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.timeout = 10000;
        xhr.onload = function () {
            var data = null;
            if (xhr.status === 200) {
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (e) {
                    data = null;
                }
            }
            if (!data || typeof data !== 'object') {
                show(RESTARTING, 'warning');
                schedule();
                return;
            }
            show(data.text, data.level);
            if (data.active) {
                schedule();
            }
        };
        xhr.onerror = xhr.ontimeout = function () {
            show(RESTARTING, 'warning');
            schedule();
        };
        xhr.send();
    }

    schedule();
}());
