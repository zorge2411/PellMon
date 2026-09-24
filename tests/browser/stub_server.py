"""Test-only CherryPy server: the real PellMonWeb handlers over FakeDbus (no daemon).

Auth is disabled and the server binds 127.0.0.1 only; this file is never part of the image.
"""
import json
import os
import socket
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import cherrypy

import Pellmonweb.pellmonweb as web
from fake_dbus import FakeDbus, GRAPH_ITEMS, write_sample_log

HTML_DIR = os.path.join(SRC, "Pellmonweb", "html")
MEDIA_DIR = os.path.join(SRC, "Pellmonweb", "media")
COLORS = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf", "#666666"]

_log_path = os.path.join(tempfile.mkdtemp(prefix="pellmon-stub-"), "pellmon.log")
write_sample_log(_log_path)

web.websockets = False
web.dbus = FakeDbus()
web.lookup = web.myLookup(directories=[HTML_DIR], dbus=web.dbus)
web.polling = True
web.db = ""
web.logtick = None
web.consumption_graph = True
web.credentials = []
web.logfile = _log_path
web.system_image_dir = os.path.join(MEDIA_DIR, "img")
web.system_image = os.path.join(MEDIA_DIR, "img", "system.svg")
web.frontpage_widgets = [["systemimage", "events"], ["graph"], ["consumption7d", "silolevel"]]
web.timeChoices = ["time1h", "time3h", "time8h", "time24h", "time3d", "time1w"]
web.timeNames = [t.replace(" ", "&nbsp;") for t in ["1 hour", "3 hours", "8 hours", "24 hours", "3 days", "1 week"]]
web.timeSeconds = [3600, 3600 * 3, 3600 * 8, 3600 * 24, 3600 * 24 * 3, 3600 * 24 * 7]
web.polldata = []
web.graph_lines = [{"name": n, "color": COLORS[i], "ds_name": n} for i, (n, _) in enumerate(GRAPH_ITEMS)]
web.colorsDict = {l["name"]: l["color"] for l in web.graph_lines}


class StubWeb(web.PellMonWeb):
    @cherrypy.expose
    def export(self, **args):
        cherrypy.response.headers["Content-Type"] = "application/json"
        now = int(time.time()) * 1000
        out = []
        for i, line in enumerate(web.graph_lines):
            out.append({"label": line["name"], "color": line["color"],
                        "data": [[now - (60 - k) * 60000, 20 + i * 5 + (k % 7)] for k in range(60)]})
        return json.dumps(out).encode("utf-8")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


if __name__ == "__main__":
    port = _free_port()
    cherrypy.config.update({
        "tools.sessions.on": True,
        "tools.auth.on": False,
        "log.screen": False,
        "engine.autoreload.on": False,
        "server.socket_host": "127.0.0.1",
        "server.socket_port": port,
    })
    app_conf = {"/media": {"tools.staticdir.on": True, "tools.staticdir.dir": MEDIA_DIR}}
    cherrypy.tree.mount(StubWeb(), "/", config=app_conf)
    cherrypy.engine.start()
    print("READY port=%d" % port, flush=True)
    cherrypy.engine.block()
