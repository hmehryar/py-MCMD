import pandas as pd
from py_mcmd_refactored.engines.gomc.parser import parse_gomc_log

def test_parse_gomc_log_creates_dataframe():
    sample_log = [
        "ETITLE:  STEP TOTAL INTRA(B) INTRA(NB) INTER(LJ) LRC TOTAL_ELECT REAL RECIP SELF CORR ENTHALPY",
        "ENER_0:   400 -862452.198853 0.0 0.0 138102.294455 0.0 -1.000550e+06 -952796.367113 1119.263862 -8.815010e+06 8.766013e+06 -279.134799"
    ]
    df = parse_gomc_log(sample_log, box_number=0, current_step=400)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "TOTAL" in df.columns
    assert abs(df.loc[0, "TOTAL"] + 862452.198853) < 1e-6
