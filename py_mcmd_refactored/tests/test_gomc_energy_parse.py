# import pandas as pd
# from py_mcmd_refactored.engines.gomc.parser import parse_gomc_log

# def test_parse_gomc_log_creates_dataframe():
#     sample_log = [
#         "ETITLE:  STEP TOTAL INTRA(B) INTRA(NB) INTER(LJ) LRC TOTAL_ELECT REAL RECIP SELF CORR ENTHALPY",
#         "ENER_0:   400 -862452.198853 0.0 0.0 138102.294455 0.0 -1.000550e+06 -952796.367113 1119.263862 -8.815010e+06 8.766013e+06 -279.134799"
#     ]
#     df = parse_gomc_log(sample_log, box_number=0, current_step=400)
#     assert isinstance(df, pd.DataFrame)
#     assert not df.empty
#     assert "TOTAL" in df.columns
#     assert abs(df.loc[0, "TOTAL"] + 862452.198853) < 1e-6


# py_mcmd_refactored/tests/test_gomc_energy_parse.py
from __future__ import annotations

from types import SimpleNamespace
import pandas as pd
import pytest

from py_mcmd_refactored.engines.gomc.energy_parse import get_gomc_energy_data


def _cfg(step=0, scale=1.0):
    # Minimal config-like object
    return SimpleNamespace(current_step=step, K_to_kcal_mol=scale)


def test_parse_energy_box0_basic():
    lines = [
        "ETITLE: ETITLE: STEP ELECT POTENTIAL VDW\n",
        "ENER_0: ENER_0: 0 1.0 2.0 3.0\n",
        "ENER_0: ENER_0: 5 10.0 20.0 30.0\n",
    ]
    cfg = _cfg(step=100, scale=0.5)
    df = get_gomc_energy_data(cfg, lines, box_number=0)

    # Columns preserved from ETITLE
    assert list(df.columns) == ["ETITLE:", "STEP", "ELECT", "POTENTIAL", "VDW"]

    # Two rows parsed
    assert len(df) == 2

    # First row values: ETITLE token, STEP offset, scaled energies
    assert df.loc[0, "ETITLE:"] == "ENER_0:"
    assert df.loc[0, "STEP"] == 100
    assert df.loc[0, "ELECT"] == pytest.approx(0.5)
    assert df.loc[0, "POTENTIAL"] == pytest.approx(1.0)
    assert df.loc[0, "VDW"] == pytest.approx(1.5)

    # Second row
    assert df.loc[1, "ETITLE:"] == "ENER_0:"
    assert df.loc[1, "STEP"] == 105
    assert df.loc[1, "ELECT"] == pytest.approx(5.0)
    assert df.loc[1, "POTENTIAL"] == pytest.approx(10.0)
    assert df.loc[1, "VDW"] == pytest.approx(15.0)


def test_parse_energy_box1_only_selects_box1():
    lines = [
        "ETITLE: ETITLE: STEP ELECT POTENTIAL VDW\n",
        "ENER_0: ENER_0: 1 1 1 1\n",
        "ENER_1: ENER_1: 2 2 3 4\n",
        "ENER_0: ENER_0: 3 5 8 13\n",
        "ENER_1: ENER_1: 4 7 11 18\n",
    ]
    cfg = _cfg(step=0, scale=1.0)
    df = get_gomc_energy_data(cfg, lines, box_number=1)

    # Only the two ENERGY_1 rows should be present
    assert len(df) == 2
    assert all(df["ETITLE:"] == "ENER_1:")
    assert list(df["STEP"]) == [2, 4]
    assert list(df["ELECT"]) == [2.0, 7.0]
    assert list(df["POTENTIAL"]) == [3.0, 11.0]
    assert list(df["VDW"]) == [4.0, 18.0]


def test_empty_energy_returns_empty_df_with_columns():
    lines = [
        "ETITLE: ETITLE: STEP ELECT POTENTIAL VDW\n",
        # no ENER_* lines
    ]
    cfg = _cfg()
    df = get_gomc_energy_data(cfg, lines, box_number=0)
    assert df.empty
    assert list(df.columns) == ["ETITLE:", "STEP", "ELECT", "POTENTIAL", "VDW"]


def test_missing_etitle_raises():
    lines = [
        "ENER_0: ENER_0: 0 1.0 2.0 3.0\n",
    ]
    cfg = _cfg()
    with pytest.raises(ValueError, match="Missing ETITLE"):
        _ = get_gomc_energy_data(cfg, lines, box_number=0)


def test_malformed_step_raises():
    lines = [
        "ETITLE: ETITLE: STEP ELECT\n",
        "ENER_0: ENER_0: not_an_int 1.0\n",
    ]
    cfg = _cfg()
    with pytest.raises(ValueError, match="Malformed STEP token"):
        _ = get_gomc_energy_data(cfg, lines, box_number=0)


def test_extra_tokens_are_ignored_beyond_headers():
    # Add an extra numeric at end of ENERGY row; header has only 4 titles
    lines = [
        "ETITLE: ETITLE: STEP ELECT POTENTIAL\n",
        "ENER_0: ENER_0: 10 2.0 4.0 999.0\n",  # trailing 999.0 should be ignored
    ]
    cfg = _cfg(step=0, scale=0.5)
    df = get_gomc_energy_data(cfg, lines, box_number=0)

    assert list(df.columns) == ["ETITLE:", "STEP", "ELECT", "POTENTIAL"]
    assert len(df) == 1
    assert df.loc[0, "ETITLE:"] == "ENER_0:"
    assert df.loc[0, "STEP"] == 10
    # scaled
    assert df.loc[0, "ELECT"] == pytest.approx(1.0)
    assert df.loc[0, "POTENTIAL"] == pytest.approx(2.0)
