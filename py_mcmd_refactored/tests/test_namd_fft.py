import sys
sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

from pathlib import Path
from config.models import SimulationConfig
from engines.namd_engine import NamdEngine
import pytest

def make_cfg(tmp: Path, **kw):
    base = dict(
        total_cycles_namd_gomc_sims=1,
        starting_at_cycle_namd_gomc_sims=0,
        simulation_type="NPT",
        gomc_use_CPU_or_GPU="CPU",
        only_use_box_0_for_namd_for_gemc=True,
        no_core_box_0=1, no_core_box_1=0,
        simulation_temp_k=298.15, simulation_pressure_bar=1.0,
        namd_minimize_mult_scalar=1, namd_run_steps=10, gomc_run_steps=10,
        set_dims_box_0_list=[25,25,25], set_angle_box_0_list=[90,90,90],
        set_dims_box_1_list=[25,25,25], set_angle_box_1_list=[90,90,90],
        starting_ff_file_list_gomc=["a.inp"], starting_ff_file_list_namd=["b.inp"],
        starting_pdb_box_0_file="box0.pdb", starting_psf_box_0_file="box0.psf",
        starting_pdb_box_1_file="box1.pdb", starting_psf_box_1_file="box1.psf",
        namd2_bin_directory=str(tmp/"bin_namd"),
        gomc_bin_directory=str(tmp/"bin_gomc"),
        path_namd_runs=str(tmp/"NAMD"),
        path_gomc_runs=str(tmp/"GOMC"),
        log_dir=str(tmp/"logs"),
    )
    base.update(kw)
    return SimulationConfig(**base)

# from engines.namd.parser import get_run0_fft_filename
def test_get_run0_fft_filename_found(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    run0 = tmp_path / "NAMD" / "00000000_a"
    run0.mkdir(parents=True, exist_ok=True)
    (run0 / "FFTW_NAMD_plan.txt").write_text("dummy")
    eng = NamdEngine(cfg, dry_run=True)
    name, dir_str = eng.get_run0_fft_filename(0)
    assert name == "FFTW_NAMD_plan.txt"
    assert dir_str.endswith("NAMD/00000000_a")

def test_get_run0_fft_filename_missing(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    eng = NamdEngine(cfg, dry_run=True)
    # name, dir_str = eng.get_run0_fft_filename(1)
    # assert name is None
    # assert dir_str.endswith("NAMD/00000000_b")
    with pytest.raises(FileNotFoundError):
        eng.get_run0_fft_filename(1)

# Target functions
from engines.namd.parser import get_run0_dir 
def test_get_run0_dir_builds_expected_path(tmp_path):
    base = tmp_path / "namd_runs"
    base.mkdir()
    # run id 0 with id_width=8 → "00000000"; box 0 → suffix 'a'
    p0 = get_run0_dir(base, box_number=0, id_width=8)
    p1 = get_run0_dir(base, box_number=1, id_width=8)
    assert p0.name.endswith("_a")
    assert p1.name.endswith("_b")
    assert p0.parent == base
    assert p1.parent == base

def test_get_run0_fft_filename_passthrough_when_not_found(tmp_path, monkeypatch):
    # Force the finder to return None regardless of files
    monkeypatch.setattr("engines.namd.parser.find_run0_fft_filename", lambda _p: None)
    cfg = make_cfg(tmp_path)
    base = tmp_path / "namd_runs"
    (base / "00000000_a").mkdir(parents=True)
    cfg.path_namd_runs=str(base)
    engine = NamdEngine(cfg, dry_run=True)
    name, run0_dir = engine.get_run0_fft_filename(0)
    assert name is None
    assert Path(run0_dir).name == "00000000_a"

