/* Phase 6: Home Assistant / MQTT page, progressive enhancement only.
 * The page works without this script. All DOM writes use textContent / createElement. */
(function () {
    'use strict';

    var statusEl = document.getElementById('mqtt-status');
    if (!statusEl) {
        return;
    }

    var STATUS_INTERVAL_MS = 5000;
    // Timeout chain: daemon test <= 8 s < server poll cap 10 s < this abort, so the server's own
    // mapped answer normally arrives first.
    var TEST_ABORT_MS = 12000;
    var TIMEOUT_MESSAGE = 'Test failed: timed out. Nothing was saved.';
    var root = (typeof webroot === 'string') ? webroot : '';

    var form = statusEl.parentNode.querySelector('form.mqtt-form');
    var saveBtn = document.querySelector('.mqtt-save');
    var testBtn = document.querySelector('.mqtt-test');
    var testResult = document.getElementById('mqtt-test-result');

    function byName(name) {
        return form ? form.querySelector('[name="' + name + '"]') : null;
    }

    function setHidden(el, hidden) {
        if (!el) {
            return;
        }
        if (hidden) {
            el.setAttribute('hidden', '');
        } else {
            el.removeAttribute('hidden');
        }
    }

    // validation summary: focus it on load so keyboard and screen reader users land on it
    var summary = document.querySelector('.mqtt-page > .alert[role="alert"][tabindex="-1"]');
    if (summary) {
        summary.focus();
    }

    // ---- (a) status refresh ----

    function squash(text) {
        return String(text).replace(/\s+/g, ' ').replace(/^ | $/g, '');
    }

    function renderStatus(view) {
        var text = (view.word ? view.word + ' ' : '') + (view.text || '');
        var cls = view.level === 'well' ? 'well' : 'alert alert-' + view.level;
        var title = view.title || '';
        if (squash(statusEl.textContent) === squash(text) && statusEl.className === cls &&
                (statusEl.getAttribute('title') || '') === title) {
            return;
        }
        while (statusEl.firstChild) {
            statusEl.removeChild(statusEl.firstChild);
        }
        if (view.glyph) {
            var glyph = document.createElement('span');
            glyph.className = 'glyphicon glyphicon-' + view.glyph;
            glyph.setAttribute('aria-hidden', 'true');
            statusEl.appendChild(glyph);
            statusEl.appendChild(document.createTextNode(' '));
        }
        if (view.word) {
            var strong = document.createElement('strong');
            strong.textContent = view.word;
            statusEl.appendChild(strong);
            statusEl.appendChild(document.createTextNode(' '));
        }
        statusEl.appendChild(document.createTextNode(view.text || ''));
        statusEl.className = cls;
        statusEl.setAttribute('title', title);
    }

    function pollStatus() {
        var url = root + '/homeassistant/status?_=' + new Date().getTime();
        fetch(url, {credentials: 'same-origin', cache: 'no-store'}).then(function (res) {
            if (!res.ok) {
                throw new Error('status ' + res.status);
            }
            return res.json();
        }).then(function (view) {
            if (view && typeof view === 'object' && view.level) {
                renderStatus(view);
            }
        }).catch(function () {
            /* leave the line unchanged */
        });
    }

    window.setInterval(pollStatus, STATUS_INTERVAL_MS);

    if (!form) {
        return;
    }

    // ---- (b) TLS / verify / port ----

    var tls = byName('tls');
    var verify = byName('tls_verify');
    var marker = byName('tls_verify_field');
    var port = byName('port');
    var verifyReason = document.getElementById('tls_verify-reason');
    var verifyWarning = document.getElementById('mqtt-verify-warning');

    function updateVerifyWarning() {
        setHidden(verifyWarning, !(tls && tls.checked && verify && !verify.checked));
    }

    if (tls) {
        tls.addEventListener('change', function () {
            var off = !tls.checked;
            if (verify) {
                verify.disabled = off;
            }
            if (marker) {
                marker.disabled = off;
            }
            if (verifyReason) {
                verifyReason.textContent = off ? ' Turn on TLS to change this.' : '';
            }
            if (port) {
                if (tls.checked && port.value === '1883') {
                    port.value = '8883';
                } else if (off && port.value === '8883') {
                    port.value = '1883';
                }
            }
            updateVerifyWarning();
        });
    }
    if (verify) {
        verify.addEventListener('change', updateVerifyWarning);
    }

    // ---- (c) commands warning ----

    var allow = byName('allow_commands');
    var commandsWarning = document.getElementById('mqtt-commands-warning');
    if (allow) {
        allow.addEventListener('change', function () {
            setHidden(commandsWarning, !allow.checked);
        });
    }

    // ---- (d) prefix mirror ----

    var prefix = byName('prefix');
    var prefixCode = document.querySelector('.mqtt-prefix-code');
    if (prefix && prefixCode) {
        prefix.addEventListener('input', function () {
            prefixCode.textContent = prefix.value;
        });
    }

    // ---- (e) Save / Test busy states ----

    form.addEventListener('submit', function (ev) {
        var submitter = ev.submitter || null;
        if (submitter && submitter === testBtn) {
            return;
        }
        if (saveBtn && !saveBtn.disabled) {
            // disable after the browser has collected the form data for this submit
            window.setTimeout(function () {
                saveBtn.textContent = 'Saving...';
                saveBtn.disabled = true;
            }, 0);
        }
    });

    var scriptErrors = [];

    function clearScriptErrors() {
        while (scriptErrors.length) {
            var entry = scriptErrors.pop();
            if (entry.group) {
                entry.group.classList.remove('has-error');
            }
            if (entry.input) {
                entry.input.removeAttribute('aria-invalid');
                var described = (entry.input.getAttribute('aria-describedby') || '').split(' ').filter(function (id) {
                    return id && id !== entry.spanId;
                });
                entry.input.setAttribute('aria-describedby', described.join(' '));
            }
            if (entry.span && entry.span.parentNode) {
                entry.span.parentNode.removeChild(entry.span);
            }
        }
    }

    function showFieldErrors(errors) {
        Object.keys(errors || {}).forEach(function (field) {
            var input = byName(field);
            if (!input) {
                return;
            }
            var group = input.closest ? input.closest('.form-group') : null;
            var spanId = field + '-error';
            var span = document.getElementById(spanId);
            var created = false;
            if (!span) {
                span = document.createElement('span');
                span.className = 'help-block';
                span.id = spanId;
                if (group) {
                    group.appendChild(span);
                }
                created = true;
            }
            span.textContent = String(errors[field]);
            var alreadyHadError = group && group.classList.contains('has-error');
            if (group) {
                group.classList.add('has-error');
            }
            input.setAttribute('aria-invalid', 'true');
            var ids = (input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
            if (ids.indexOf(spanId) === -1) {
                ids.push(spanId);
                input.setAttribute('aria-describedby', ids.join(' '));
            }
            if (created || !alreadyHadError) {
                scriptErrors.push({group: alreadyHadError ? null : group, input: input, span: created ? span : null,
                                   spanId: spanId});
            }
        });
    }

    function showTestResult(message, ok) {
        if (!testResult) {
            return;
        }
        while (testResult.firstChild) {
            testResult.removeChild(testResult.firstChild);
        }
        testResult.className = 'mqtt-test-result ' + (ok ? 'text-success' : 'text-danger');
        var glyph = document.createElement('span');
        glyph.className = 'glyphicon ' + (ok ? 'glyphicon-ok' : 'glyphicon-remove');
        glyph.setAttribute('aria-hidden', 'true');
        testResult.appendChild(glyph);
        testResult.appendChild(document.createTextNode(' ' + message));
    }

    function restoreTestButton() {
        testBtn.textContent = 'Test connection';
        testBtn.disabled = false;
        testBtn.removeAttribute('aria-busy');
    }

    if (testBtn) {
        testBtn.addEventListener('click', function (ev) {
            ev.preventDefault();
            if (testBtn.disabled) {
                return;
            }
            clearScriptErrors();
            testBtn.textContent = 'Testing...';
            testBtn.disabled = true;
            testBtn.setAttribute('aria-busy', 'true');
            if (testResult) {
                testResult.className = 'mqtt-test-result';
                testResult.textContent = 'Testing the connection...';
            }

            var data = new FormData(form);
            data.append('format', 'json');
            var url = testBtn.getAttribute('formaction') || (root + '/homeassistant/test');
            var controller = (typeof AbortController === 'function') ? new AbortController() : null;
            var timer = window.setTimeout(function () {
                if (controller) {
                    controller.abort();
                }
            }, TEST_ABORT_MS);
            var options = {method: 'POST', body: data, credentials: 'same-origin'};
            if (controller) {
                options.signal = controller.signal;
            }

            fetch(url, options).then(function (res) {
                return res.json();
            }).then(function (result) {
                if (result.state === 'invalid') {
                    showFieldErrors(result.errors);
                }
                showTestResult(String(result.message || ''), result.state === 'ok');
            }).catch(function () {
                showTestResult(TIMEOUT_MESSAGE, false);
            }).then(function () {
                window.clearTimeout(timer);
                restoreTestButton();
            });
        });
    }
})();
