# 11-04 Summary: entities

- 26 entities appended after the original 21 (22 sensors, 4 numbers); object ids, topics and unique ids of the originals untouched.
- Device/state classes and units checked against Home Assistant core `sensor/const.py` (dev branch): duration accepts d/s, weight kg/g, `volume_flow_rate` needs `L/s` (capital L, Scotte reports `l/s`), timestamp takes no unit or state class. A test encodes these rules.
- Writable: `hotwater_temp_set`, `hotwater_temp_diff`, `magazine_content_set` (item `magazine_content`), `silo_reset_level`. No blower/oxygen/regulator writes (tested).
- Bridge: logs a warning when a write is accepted by `Database.set_value` but the value read back differs (plugin setters can return 'error' while set_value still says OK); the readback already snaps HA to the real value.
- Tests: presence matrix, upgrade adds only new discovery, commands-off removal, range limits, unapplied write.
