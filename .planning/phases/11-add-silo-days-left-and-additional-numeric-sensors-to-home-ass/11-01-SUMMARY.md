# 11-01 Summary: entity value kind and numeric publish guard

- `Entity` gained a `kind` field (numeric / text / timestamp / none); `mode` is text, buttons are none.
- `entities.is_publishable()` and a guard at the top of `Bridge._publish_state`, so the refresh, change-callback and command-readback paths are all covered. Mutation-checked: removing the guard fails the new test.
- Golden file `tests/Pellmonsrv/plugins/data/ha_golden_v6.json` proves the original 21 discovery payloads are byte-identical (commands on and off).
- Entity-count literals in `test_homeassistant_entities.py` replaced by values derived from `ENTITIES`.
