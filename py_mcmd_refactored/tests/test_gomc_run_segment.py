# py_mcmd_refactored/tests/test_gomc_run_segment.py

from __future__ import annotations

from pathlib import Path
import pytest

from config.models import SimulationConfig
from engines.gomc_engine import GomcEngine
from orchestrator.state import RunState, PmeDims


def _cfg(tmp_path: Path, **kw) -> SimulationConfig:
    base = dict(
        total_cycles_namd_gomc_sims=2,
        starting_at_cycle_namd_gomc_sims=0,
        simulation_type="NPT",
        gomc_use_CPU_or_GPU="CPU",
        only_use_box_0_for_namd_for_gemc=True,
        no_core_box_0=2,
        no_core_box_1=2,
        simulation_temp_k=298.15,
        simulation_pressure_bar=1.0,
        namd_minimize_mult_scalar=1,
        namd_run_steps=10,
        gomc_run_steps=5,
        # derived fields
        namd_minimize_steps=10,
        namd_rst_dcd_xst_steps=10,
        namd_console_blkavg_e_and_p_steps=10,
        gomc_rst_coor_ckpoint_steps=5,
        gomc_console_blkavg_hist_steps=5,
        gomc_hist_sample_steps=5,
        set_dims_box_0_list=[25.0, 25.0, 25.0],
        set_dims_box_1_list=[25.0, 25.0, 25.0],
        set_angle_box_0_list=[90, 90, 90],
        set_angle_box_1_list=[90, 90, 90],
        starting_ff_file_list_gomc=["ff_gomc.inp"],
        starting_ff_file_list_namd=["ff_namd.inp"],
        starting_pdb_box_0_file="box0.pdb",
        starting_psf_box_0_file="box0.psf",
        starting_pdb_box_1_file="box1.pdb",
        starting_psf_box_1_file="box1.psf",
        namd2_bin_directory=str(tmp_path / "bin_namd"),
        gomc_bin_directory=str(tmp_path / "bin_gomc"),
        path_namd_runs=str(tmp_path / "NAMD"),
        path_gomc_runs=str(tmp_path / "GOMC"),
        path_namd_template=str(tmp_path / "templates" / "namd.inp"),
        path_gomc_template=str(tmp_path / "templates" / "gomc.inp"),
        log_dir=str(tmp_path / "logs"),
        total_no_cores=4,
        starting_sims_namd_gomc=0,
        total_sims_namd_gomc=4,
    )
    base.update(kw)
    return SimulationConfig(**base)


def _state() -> RunState:
    st = RunState(current_step=0)
    st.pme_box0 = PmeDims()
    st.pme_box1 = PmeDims()
    return st


@pytest.fixture
def monkeypatch_writer(monkeypatch):
    """Patch write_gomc_conf_file so run_segment doesn't require templates."""
    import engines.gomc_engine as ge

    def fake_write_gomc_conf_file(
        python_file_directory,
        path_gomc_runs,
        run_no,
        *args,
        **kwargs,
    ):
        run_root = Path(path_gomc_runs)
        run_root.mkdir(parents=True, exist_ok=True)
        run_dir = run_root / f"run_{int(run_no):02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "in.conf").write_text("# dummy\n", encoding="utf-8")
        return str(run_dir)

    monkeypatch.setattr(ge, "write_gomc_conf_file", fake_write_gomc_conf_file)
    return True


def test_gomc_run_segment_updates_step_and_sets_dir(tmp_path: Path, monkeypatch_writer):
    cfg = _cfg(tmp_path)
    eng = GomcEngine(cfg, dry_run=True)
    st = _state()

    res = eng.run_segment(run_no=1, state=st)

    assert st.current_step == cfg.gomc_run_steps
    assert st.gomc_dir is not None
    assert (Path(res["gomc_dir"]) / "out.dat").exists()


def test_gomc_run_segment_calls_compare_when_values_exist(tmp_path: Path, monkeypatch, monkeypatch_writer):
    cfg = _cfg(tmp_path)
    eng = GomcEngine(cfg, dry_run=True)
    st = _state()

    # seed NAMD finals so continuity check can trigger
    st.energy_box0.namd_potential_final = 10.0
    st.energy_box0.namd_vdw_plus_elec_final = 20.0

    calls = []
    import engines.gomc_engine as ge

    def fake_compare(cfg_, namd_pot_f, gomc_pot_i, namd_vpe_f, gomc_vpe_i, run_no, box_number):
        calls.append((namd_pot_f, gomc_pot_i, namd_vpe_f, gomc_vpe_i, run_no, box_number))

    monkeypatch.setattr(ge, "compare_namd_gomc_energies", fake_compare)

    # patch energy parsing so gomc_pot_i/gomc_vpe_i exist deterministically
    monkeypatch.setattr(ge, "get_gomc_energy_data", lambda lines, box: object())
    monkeypatch.setattr(
        ge,
        "get_gomc_energy_data_kcal_per_mol",
        lambda df: (None, None, None, None, 100.0, 101.0, None, None, None, None, 200.0, 201.0),
    )

    eng.run_segment(run_no=1, state=st)

    assert len(calls) == 1
    assert calls[0][-2:] == (1, 0)


def test_gomc_run_segment_two_box_gemc_parses_box1(tmp_path: Path, monkeypatch, monkeypatch_writer):
    cfg = _cfg(tmp_path, simulation_type="GEMC")
    eng = GomcEngine(cfg, dry_run=True)
    st = _state()

    import engines.gomc_engine as ge

    # return "df" as the box number
    monkeypatch.setattr(ge, "get_gomc_energy_data", lambda lines, box: box)

    def fake_metrics(df):
        if df == 0:
            return (None, None, None, None, 10.0, 11.0, None, None, None, None, 20.0, 21.0)
        return (None, None, None, None, 30.0, 31.0, None, None, None, None, 40.0, 41.0)

    monkeypatch.setattr(ge, "get_gomc_energy_data_kcal_per_mol", fake_metrics)

    eng.run_segment(run_no=1, state=st)

    assert st.energy_box0.gomc_potential_initial == 10.0
    assert st.energy_box1.gomc_potential_initial == 30.0
    assert st.energy_box0.gomc_vdw_plus_elec_initial == 20.0
    assert st.energy_box1.gomc_vdw_plus_elec_initial == 40.0