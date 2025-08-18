import sys
sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

import pytest
from pathlib import Path
import json

from config.models import load_simulation_config, SimulationConfig
# ---- helpers ----
def repo_root() -> Path:
    # test file is at: <repo>/py_mcmd_refactored/tests/test_config.py
    # parents[0]=.../tests, [1]=.../py_mcmd_refactored, [2]=<repo>
    return Path(__file__).resolve().parents[2]

def make_cfg(**overrides) -> SimulationConfig:
    base = dict(
        total_cycles_namd_gomc_sims=3,
        starting_at_cycle_namd_gomc_sims=0,
        gomc_use_CPU_or_GPU="CPU",
        simulation_type="NPT",
        only_use_box_0_for_namd_for_gemc=True,
        no_core_box_0=4,
        no_core_box_1=0,
        simulation_temp_k=250,
        simulation_pressure_bar=1.0,
        GCMC_ChemPot_or_Fugacity="ChemPot",
        GCMC_ChemPot_or_Fugacity_dict={"TIP3": -1000, "WAT": -2000},
        namd_minimize_mult_scalar=1,
        namd_run_steps=200,
        gomc_run_steps=20,
        set_dims_box_0_list=[25.0, 25.0, 25.0],
        set_dims_box_1_list=[25, 25, 25],
        set_angle_box_0_list=[90, 90, 90],
        set_angle_box_1_list=[90, 90, 90],
        starting_ff_file_list_gomc=["required_data/input/OPC_FF_GOMC.inp"],
        starting_ff_file_list_namd=["required_data/input/OPC_FF_NAMD.inp"],
        starting_pdb_box_0_file="required_data/input/OPC_equil_BOX_0_restart.pdb",
        starting_psf_box_0_file="required_data/input/OPC_equil_BOX_0_restart.psf",
        starting_pdb_box_1_file="required_data/equilb_box_298K/TIPS3P_reservoir_box_1.pdb",
        starting_psf_box_1_file="required_data/equilb_box_298K/TIPS3P_reservoir_box_1.psf",
        namd2_bin_directory="../NAMD_2.14_Linux-x86_64-multicore",
        gomc_bin_directory="../GOMC/bin",
    )
    base.update(overrides)
    return SimulationConfig(**base)

def test_load_config():
    # Resolve the JSON file path *relative* to the project root
    project_root = Path(__file__).parent.parent.parent
    # config_path = project_root / "user_input_NAMD_GOMC.json"
    config_path = repo_root() / "user_input_NAMD_GOMC.json"
    # sanity check
    assert config_path.exists(), f"Config not found at {config_path}"
    cfg = load_simulation_config(config_path)
    assert isinstance(cfg, SimulationConfig)
    # spot‐check a value you know exists
    assert cfg.total_cycles_namd_gomc_sims > 0


# ---- tolerances defaults & overrides ----
def test_tolerances_defaults():
    cfg = make_cfg()
    assert cfg.allowable_error_fraction_vdw_plus_elec == pytest.approx(5e-3)
    assert cfg.allowable_error_fraction_potential == pytest.approx(5e-3)
    assert cfg.max_absolute_allowable_kcal_fraction_vdw_plus_elec == pytest.approx(0.5)


def test_tolerances_overrides():
    cfg = make_cfg(
        allowable_error_fraction_vdw_plus_elec=1e-2,
        allowable_error_fraction_potential=2e-2,
        max_absolute_allowable_kcal_fraction_vdw_plus_elec=0.75,
    )
    assert cfg.allowable_error_fraction_vdw_plus_elec == pytest.approx(1e-2)
    assert cfg.allowable_error_fraction_potential == pytest.approx(2e-2)
    assert cfg.max_absolute_allowable_kcal_fraction_vdw_plus_elec == pytest.approx(0.75)


# ---- derived per-engine params ----
def test_derived_params_basic():
    cfg = make_cfg()  # namd_run_steps=200, gomc_run_steps=20
    # GOMC
    assert cfg.gomc_console_blkavg_hist_steps == 20
    assert cfg.gomc_rst_coor_ckpoint_steps == 20
    assert cfg.gomc_hist_sample_steps == 2  # 20/10 = 2 < 500
    # NAMD
    assert cfg.namd_rst_dcd_xst_steps == 200
    assert cfg.namd_console_blkavg_e_and_p_steps == 200


@pytest.mark.parametrize(
    "gomc_steps, expected_hist_sample",
    [
        (10, 1),          # 10/10 = 1
        (100, 10),        # 100/10 = 10
        (5000, 500),      # 5000/10 = 500 → boundary
        (6000, 500),      # 6000/10 = 600 → capped at 500
        (0, 0),           # guard for zero
        (1, 0),           # int(1/10) = 0
        (9, 0),           # int(9/10) = 0
    ],
)
def test_gomc_hist_sample_rule(gomc_steps, expected_hist_sample):
    cfg = make_cfg(gomc_run_steps=gomc_steps)
    assert cfg.gomc_hist_sample_steps == expected_hist_sample


def test_zero_steps_edge_cases():
    cfg = make_cfg(namd_run_steps=0, gomc_run_steps=0)
    assert cfg.namd_rst_dcd_xst_steps == 0
    assert cfg.namd_console_blkavg_e_and_p_steps == 0
    assert cfg.gomc_console_blkavg_hist_steps == 0
    assert cfg.gomc_rst_coor_ckpoint_steps == 0
    assert cfg.gomc_hist_sample_steps == 0


def test_load_from_json_constructor_logic(tmp_path: Path):
    # Ensure load_simulation_config applies constructor-derived values
    data = make_cfg().model_dump()  # Pydantic v2
    data["gomc_run_steps"] = 6000  # should cap hist_sample at 500
    json_path = tmp_path / "user_input.json"
    json_path.write_text(json.dumps(data, indent=2))

    cfg = load_simulation_config(str(json_path))
    assert cfg.gomc_run_steps == 6000
    assert cfg.gomc_hist_sample_steps == 500