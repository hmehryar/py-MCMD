import sys
sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

# tests/test_models.py
import json
import pytest
from pydantic import ValidationError
from config.models import SimulationConfig, load_simulation_config

# Helper: minimal valid configuration as a Python dict
def minimal_config():
    return {
        "total_cycles_namd_gomc_sims": 2,
        "starting_at_cycle_namd_gomc_sims": 0,
        "gomc_use_CPU_or_GPU": "CPU",
        "simulation_type": "NVT",
        "only_use_box_0_for_namd_for_gemc": True,
        "no_core_box_0": 1,
        "no_core_box_1": 0,
        "simulation_temp_k": 300.0,
        "simulation_pressure_bar": 1.0,
        "GCMC_ChemPot_or_Fugacity": None,
        "GCMC_ChemPot_or_Fugacity_dict": None,
        "namd_minimize_mult_scalar": 2,
        "namd_run_steps": 100,
        "gomc_run_steps": 100,
        "set_dims_box_0_list": [10.0, 10.0, 10.0],
        "set_dims_box_1_list": [10.0, 10.0, 10.0],
        "set_angle_box_0_list": [90, 90, 90],
        "set_angle_box_1_list": [90, 90, 90],
        "starting_ff_file_list_gomc": ["ff1.dat"],
        "starting_ff_file_list_namd": ["ff2.dat"],
        "starting_pdb_box_0_file": "box0.pdb",
        "starting_psf_box_0_file": "box0.psf",
        "starting_pdb_box_1_file": None,
        "starting_psf_box_1_file": None,
        "namd2_bin_directory": "bin/namd",
        "gomc_bin_directory": "bin/gomc"
    }


def test_valid_minimal_config(tmp_path):
    # Write JSON to temporary file
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(minimal_config()))

    # Should load without errors
    cfg = load_simulation_config(str(cfg_path))
    assert isinstance(cfg, SimulationConfig)
    assert cfg.total_cycles_namd_gomc_sims == 2
    # Lists normalized
    assert cfg.set_dims_box_0_list == [10.0, 10.0, 10.0]
    assert cfg.set_angle_box_1_list == [90, 90, 90]


def test_negative_cycles_raises():
    data = minimal_config()
    data['total_cycles_namd_gomc_sims'] = -1
    with pytest.raises(ValidationError) as exc:
        SimulationConfig(**data)
    assert 'total_cycles_namd_gomc_sims' in str(exc.value)


def test_invalid_gomc_device():
    data = minimal_config()
    data['gomc_use_CPU_or_GPU'] = 'TPU'
    with pytest.raises(ValidationError):
        SimulationConfig(**data)


def test_invalid_simulation_type():
    data = minimal_config()
    data['simulation_type'] = 'FOO'
    with pytest.raises(ValidationError):
        SimulationConfig(**data)


def test_dims_list_length():
    data = minimal_config()
    data['set_dims_box_0_list'] = [1.0, 2.0]  # wrong length
    with pytest.raises(ValidationError):
        SimulationConfig(**data)


def test_angle_list_invalid_value():
    data = minimal_config()
    data['set_angle_box_1_list'] = [90, 60, 90]
    with pytest.raises(ValidationError):
        SimulationConfig(**data)


def test_gemc_requires_two_box_cores():
    data = minimal_config()
    data['simulation_type'] = 'GEMC'
    data['only_use_box_0_for_namd_for_gemc'] = False
    data['no_core_box_1'] = 0
    with pytest.raises(ValueError) as exc:
        SimulationConfig(**data)
    assert 'no_core_box_1 must be > 0' in str(exc.value)


def test_npt_pressure_negative():
    data = minimal_config()
    data['simulation_type'] = 'NPT'
    data['simulation_pressure_bar'] = -5.0
    with pytest.raises(ValueError):
        SimulationConfig(**data)


def test_gcmc_missing_fields():
    data = minimal_config()
    data['simulation_type'] = 'GCMC'
    # Remove chempot fields
    data['GCMC_ChemPot_or_Fugacity'] = None
    data['GCMC_ChemPot_or_Fugacity_dict'] = None
    with pytest.raises(ValueError):
        SimulationConfig(**data)


def test_gcmc_negative_fugacity_value():
    data = minimal_config()
    data['simulation_type'] = 'GCMC'
    data['GCMC_ChemPot_or_Fugacity'] = 'Fugacity'
    data['GCMC_ChemPot_or_Fugacity_dict'] = {'x': -1.0}
    with pytest.raises(ValueError):
        SimulationConfig(**data)
