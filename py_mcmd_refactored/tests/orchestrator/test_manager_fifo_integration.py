from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from config.models import SimulationConfig
import orchestrator.manager as mgr


def make_cfg(tmp_path: Path, **overrides) -> SimulationConfig:
    base = dict(
        total_cycles_namd_gomc_sims=2,
        starting_at_cycle_namd_gomc_sims=0,
        gomc_use_CPU_or_GPU="CPU",
        simulation_type="NPT",
        only_use_box_0_for_namd_for_gemc=True,
        no_core_box_0=2,
        no_core_box_1=0,
        simulation_temp_k=250.0,
        simulation_pressure_bar=1.0,
        GCMC_ChemPot_or_Fugacity="ChemPot",
        GCMC_ChemPot_or_Fugacity_dict={"WAT": -2000},
        namd_minimize_mult_scalar=1,
        namd_run_steps=10,
        gomc_run_steps=5,
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
        log_dir=str(tmp_path / "logs"),
        total_no_cores=2,
        starting_sims_namd_gomc=0,
        total_sims_namd_gomc=4,
        developer_mode=False,
    )
    base.update(overrides)
    return SimulationConfig(**base)


class FakeFifoStore:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.resources = {}

    def prepare_step(self, engine, step_id):
        self.calls.append(("prepare", engine, step_id))
        endpoints = {
            "box0.out.dat": SimpleNamespace(fifo_path=Path(f"/tmp/{engine}_{step_id}_box0.out.dat")),
            "box1.out.dat": SimpleNamespace(fifo_path=Path(f"/tmp/{engine}_{step_id}_box1.out.dat")),
            "out.dat": SimpleNamespace(fifo_path=Path(f"/tmp/{engine}_{step_id}_out.dat")),
        }
        res = SimpleNamespace(engine=engine, step_id=step_id, endpoints=endpoints)
        self.resources[(engine, step_id)] = res
        return res

    def finalize_step_success(self, engine, step_id):
        self.calls.append(("success", engine, step_id))

    def finalize_step_failure(self, engine, step_id):
        self.calls.append(("failure", engine, step_id))

    def cleanup_step(self, engine, step_id):
        self.calls.append(("cleanup_step", engine, step_id))

    def cleanup_all(self):
        self.calls.append(("cleanup_all",))


def test_orchestrator_retains_only_latest_successful_step_per_engine(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mgr, "FifoStore", FakeFifoStore)

    cfg = make_cfg(tmp_path)
    orch = mgr.SimulationOrchestrator(cfg, dry_run=True)

    monkeypatch.setattr(
        orch.namd,
        "run_segment",
        lambda *, run_no, state, fifo_resources=None: {"run_no": run_no},
        raising=True,
    )
    monkeypatch.setattr(
        orch.gomc,
        "run_segment",
        lambda *, run_no, state, fifo_resources=None: {"run_no": run_no},
        raising=True,
    )

    orch.run()

    assert ("prepare", "NAMD", "0000000000") in orch.fifo_store.calls
    assert ("prepare", "GOMC", "0000000001") in orch.fifo_store.calls
    assert ("prepare", "NAMD", "0000000002") in orch.fifo_store.calls
    assert ("prepare", "GOMC", "0000000003") in orch.fifo_store.calls

    assert ("cleanup_step", "NAMD", "0000000000") in orch.fifo_store.calls
    assert ("cleanup_step", "GOMC", "0000000001") in orch.fifo_store.calls
    assert ("cleanup_all",) in orch.fifo_store.calls


def test_orchestrator_cleans_current_fifo_step_on_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mgr, "FifoStore", FakeFifoStore)

    cfg = make_cfg(tmp_path)
    orch = mgr.SimulationOrchestrator(cfg, dry_run=True)

    monkeypatch.setattr(
        orch.namd,
        "run_segment",
        lambda *, run_no, state, fifo_resources=None: {"run_no": run_no},
        raising=True,
    )

    def boom(*, run_no, state, fifo_resources=None):
        raise RuntimeError("gomc failed")

    monkeypatch.setattr(orch.gomc, "run_segment", boom, raising=True)

    with pytest.raises(RuntimeError, match="gomc failed"):
        orch.run()

    assert ("success", "NAMD", "0000000000") in orch.fifo_store.calls
    assert ("failure", "GOMC", "0000000001") in orch.fifo_store.calls
    assert ("cleanup_all",) in orch.fifo_store.calls