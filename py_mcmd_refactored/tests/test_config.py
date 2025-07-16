import sys
sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

import pytest
from pathlib import Path
from config.models import load_simulation_config, SimulationConfig

def test_load_config():
    # Resolve the JSON file path *relative* to the project root
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "user_input_NAMD_GOMC.json"

    # sanity check
    assert config_path.exists(), f"Config not found at {config_path}"
    cfg = load_simulation_config(config_path)
    assert isinstance(cfg, SimulationConfig)
    # spot‐check a value you know exists
    assert cfg.total_cycles_namd_gomc_sims > 0