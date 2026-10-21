"""Error code categories and station states."""

from __future__ import annotations

import json

from protocol.enums import BagState, CleanWaterTankState, DetergentState, DustBoxState, SewageTankState
from protocol.errors import ASSETS, ERROR_CATEGORIES, error_category, error_hex
from protocol.models import decode_device_base_status


def test_table_uses_known_categories_only() -> None:
    table = json.loads((ASSETS / "errors.json").read_text(encoding="utf-8"))
    assert len(table) > 200
    assert set(table.values()) <= set(ERROR_CATEGORIES)
    assert all(key == f"0x{int(key, 16):08X}" for key in table), "normalised hex keys"


def test_lookup() -> None:
    assert error_category(0x02100063) == "stuck"
    assert error_category(0x01010036) == "dirty_water_full"
    assert error_category(0x02020031) == "roller_brush"
    assert error_category(0x02100018) == "return_to_dock", "not 'charging' despite the contacts hint"
    assert error_category(1201) == "unknown"
    assert error_hex(0x02100063) == "0x02100063"


def test_station_states_from_the_real_status(fixture_bin) -> None:
    st = decode_device_base_status(fixture_bin("device_base_status"))
    assert st.clean_water is CleanWaterTankState.NORMAL
    assert st.dirty_water is SewageTankState.NORMAL
    assert st.detergent is DetergentState.OK
    assert st.dust_box is DustBoxState.NORMAL
    assert st.station_bag is BagState.OK
    assert not st.has_field(21), "this robot reports no dust bag of its own"
    assert st.dust_bag is BagState.UNSPECIFIED
