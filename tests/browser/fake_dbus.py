"""Canned stand-in for Pellmonweb.pellmonweb.Dbus_handler (no daemon needed)."""
import json
import time

from plugin_templates import find_template

GRAPH_ITEMS = [
    ("boiler_temp", "Boiler temperature measured value"),
    ("smoke_temp", "Flue gas temperature at the chimney"),
    ("return_temp", "Return water temperature to boiler"),
    ("room_temp", "Room temperature reference sensor"),
    ("oxygen", "Oxygen level in the flue gas"),
    ("power", "Current burner power output percent"),
    ("feeder_time", "Feeder screw run time per cycle"),
    ("flame", "Flame photo sensor light intensity"),
]

LONG = "Very long parameter name that must wrap on narrow screens"


def _item(name, kind, i):
    item = {
        "name": name,
        "type": kind,
        "longname": "%s %02d" % (LONG, i),
        "description": "Description of %s, long enough to wrap onto several lines on a phone." % name,
        "unit": "C",
        "label": name,
    }
    return item


def _full_db():
    items = []
    for i, (name, label) in enumerate(GRAPH_ITEMS):
        item = _item(name, "R", i)
        item["label"] = label
        items.append(item)
    for i in range(len(GRAPH_ITEMS), 12):
        items.append(_item("data_%02d" % i, "R", i))
    for i in range(8):
        item = _item("param_%02d" % i, "R/W", i)
        if i % 2 == 0:
            item["get_enum_list"] = [("0", "Off"), ("1", "Low"), ("2", "High")]
        else:
            item["min"] = "0"
            item["max"] = "100"
        items.append(item)
    for i in range(4):
        items.append(_item("cmd_%02d" % i, "W", i))
    return items


def _flot_points(base, span):
    now = int(time.time()) * 1000
    return [[now - (60 - k) * 60000, base + (k % span)] for k in range(60)]


class FakeDbus:
    def __init__(self):
        self._db = _full_db()

    def getItem(self, name):
        if name == "burner_connection":
            return "connected"
        if name == "burner_connection_reason":
            return ""
        if name in ("consumptionData24h", "consumptionData7d", "consumptionData8w", "consumptionData1y"):
            now = int(time.time()) * 1000
            bars = [[now - (24 - k) * 3600000, 1.5 + (k % 5) * 0.4] for k in range(24)]
            return json.dumps({"bardata": [{"data": bars}], "total": 32.5, "average": 4.6})
        if name == "siloLevelData":
            return json.dumps({"graphdata": [{"data": _flot_points(120, 30)}], "silo_level": 120, "silo_days_left": 14})
        return "42.5"

    def setItem(self, name, value):
        return "OK"

    def getdb(self):
        return [i["name"] for i in self._db] + ["burner_connection", "burner_connection_reason"]

    def getDBwithTags(self, tags):
        return self.getdb()

    def getFullDB(self, tags):
        return [dict(i) for i in self._db]

    def getMenutags(self):
        return ["Overview", "Burner", "Blower settings", "Oxygen regulation",
                "Fuel feeding", "Ignition", "Cleaning", "Water heating"]

    def getPlugins(self, name):
        return find_template(name)

    def get_setting(self, key):
        return "system.svg"

    def set_setting(self, key, value):
        return True


def write_sample_log(path):
    lines = []
    for i in range(40):
        lines.append("2026-09-24 10:%02d:%02d pellMon INFO Sample event number %d from the burner" % (i // 60, i % 60, i))
    lines.append("2026-09-24 11:00:00 " + "x" * 200)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
