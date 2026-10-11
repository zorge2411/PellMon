# Quick 261011-hdb Summary: Home Assistant dashboard generator

**Status:** done; pending a real import into Home Assistant with the user's id list.

- `tools/ha_dashboard.py`: resolves entity ids, builds the dashboard data, emits YAML; options `--ids`, `--prefix`,
  `--map`, `--include`, `--silo-capacity`, `--no-apexcharts`, `--no-controls`, `--admin-user`, `--title`, `-o`.
- `config/ha-dashboard.example.yaml`: output with assumed ids and silo capacity 220; a test keeps it equal to the generator.
- `tests/test_ha_dashboard.py` (28): coverage guard (every entity placed), absent entities, card/feature whitelist,
  forecast and consumption series, controls and confirmations, id resolution with overlapping names, emitter round
  trip with PyYAML (PyYAML added to CI and requirements-dev).
- `DEPLOY-PI.md`: how to get the id list, generate, and paste; docs test added.

Found while building: the "Oxygen Level" / "Desired Oxygen Level" and "Power" / "Min Power" / "Max Power" names overlap
when HA prefixes the device name, so matching claims longer names first. Heading badges do not accept `show_name`.

Not verified: loading the YAML into a real Home Assistant (no instance here); the user's actual entity ids.
