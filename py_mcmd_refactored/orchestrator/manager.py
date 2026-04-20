# orchestrator/manager.py
import os
import logging
from datetime import datetime
from pathlib import Path

from version import get_version

from utils.path import format_cycle_id
from config.models import SimulationConfig
from .state import RunState, PmeDims


# you’ll wire in your engines once they exist:
# from engines.namd_engine import NAMDEngine
# from engines.gomc_engine import GOMCEngine
from engines.base import Engine
from engines.gomc_engine import GomcEngine
from engines.namd_engine import NamdEngine
from utils.fifo_store import FifoStore,FifoStepResources

_FIFO_OUTPUT_BASENAMES_BY_ENGINE = {
    # These are the outputs currently routed through the centralized runner.
    # The same pattern can be extended to restart artifacts as they are moved
    # from writer-owned filenames to store-owned endpoints.
    "NAMD": ["box0.out.dat", "box1.out.dat"],
    "GOMC": ["out.dat"],
}

import time
import inspect


try:
    from orchestrator.restart import compute_start_context, apply_start_context
except Exception:  # pragma: no cover
    compute_start_context = None
    apply_start_context = None

class SimulationOrchestrator:
    # def __init__(self, cfg: SimulationConfig):
    #     self.cfg = cfg
    #     self.logger = logging.getLogger(self.__class__.__name__)
    #     # instantiate your engine wrappers here:
    #     # self.namd = NAMDEngine(cfg)
    #     # self.gomc = GOMCEngine(cfg)

    logger = logging.getLogger(__name__)

    def __init__(self, cfg: SimulationConfig, dry_run: bool = False):
        self.cfg = cfg
        # Central mutable state for the legacy run_no loop
        self.state = RunState.from_config(cfg)
        self._time_stats_lines = []

        # Propagated execution strategy for NAMD (used later when planning two-box GEMC runs)
        self.namd_simulation_order = getattr(cfg, "namd_simulation_order", "series")

        self.dry_run = dry_run

        self.developer_mode = bool(getattr(cfg, "developer_mode", False))
        # self.fifo_store = FifoStore(
        #     root_dir=Path(self.cfg.log_dir) / ".fifo_store",
        #     output_basenames_by_engine=_FIFO_OUTPUT_BASENAMES_BY_ENGINE,
        #     developer_mode=self.developer_mode,
        #     dual_write_path_factory=self._fifo_dual_write_path,
        #     logger=self.logger,
        # )
        self.fifo_store = FifoStore(
            disk_roots={
                "NAMD": Path(self.cfg.path_namd_runs),
                "GOMC": Path(self.cfg.path_gomc_runs),
            },
            developer_mode=self.developer_mode,
            logger=self.logger,
        )
        self._last_successful_fifo_step_by_engine = {
            "NAMD": None,
            "GOMC": None,
        }

        self.namd = NamdEngine(cfg, "NAMD", dry_run=dry_run)
        self.gomc = GomcEngine(cfg, "GOMC", dry_run=dry_run)

        self.total_cycles = int(getattr(cfg, "total_cycles_namd_gomc_sims", 0))
        self.start_cycle = int(getattr(cfg, "starting_at_cycle_namd_gomc_sims", 0))
        self.namd_steps  = int(getattr(cfg, "namd_run_steps", 0))
        self.gomc_steps  = int(getattr(cfg, "gomc_run_steps", 0))

        # Derived (legacy names)
        self.total_sims_namd_gomc = int(cfg.total_sims_namd_gomc)          # 2 * total_cycles
        self.starting_sims_namd_gomc = int(cfg.starting_sims_namd_gomc)    # 2 * start_cycle

        if self.total_cycles <= 0:
            raise ValueError("total_cycles_namd_gomc_sims must be > 0")

        # NEW: ensure run directories exist (and warn if stale)
        self._prepare_run_dirs()
        self._setup_run_logging()     # NEW: file logging with header
        self._emit_start_header()     # NEW: writes start time + binaries


        self.logger.info(
            "Initialized orchestrator: total_cycles=%s, start_cycle=%s, namd_steps=%s, gomc_steps=%s, dry_run=%s, total_sims=%s, start_sims=%s, namd_simulation_order=%s",
            self.total_cycles, self.start_cycle, self.namd_steps, self.gomc_steps, self.dry_run, self.total_sims_namd_gomc, self.starting_sims_namd_gomc, self.namd_simulation_order
        )
        self._emit_core_allocation_header()   # NEW: log core allocations & warnings
    def _emit_core_allocation_header(self) -> None:
        st = self.cfg.simulation_type
        only_box0 = self.cfg.only_use_box_0_for_namd_for_gemc
        nc0 = self.cfg.no_core_box_0
        nc1 = self.cfg.no_core_box_1
        eff_nc1 = self.cfg.effective_no_core_box_1
        total = self.cfg.total_no_cores

        if st == "GEMC" and not only_box0:
            if nc1 == 0:
                msg = (
                    "*************************************************\n"
                    f"no_core_box_0 = {nc0}\n"
                    "WARNING: the number of CPU cores listed for box 1 is zero (0), and should be an "
                    "integer > 0, or the NAMD simulation for box 1 will not run.\n"
                    f"no_core_box_1 = {nc1}\n"
                    "*************************************************"
                )
                self.logger.warning(msg)
            else:
                msg = (
                    "*************************************************\n"
                    f"no_core_box_0 = {nc0}\n"
                    f"no_core_box_1 = {nc1}\n"
                    "*************************************************"
                )
                self.logger.info(msg)
        else:
            # Not using box 1 (either not GEMC, or GEMC w/ only box 0)
            if nc1 != 0:
                msg = (
                    "*************************************************\n"
                    f"no_core_box_0 = {nc0}\n"
                    "WARNING: the number of CPU cores listed for box 1 are not being used.\n"
                    f"no_core_box_1 = {nc1}\n"
                    "*************************************************"
                )
                self.logger.warning(msg)

        self.logger.info(f"[Core Allocation] effective_no_core_box_1={eff_nc1}, total_no_cores={total}")

    def _setup_run_logging(self) -> None:
        """Create a per-run log file and attach a FileHandler to root logger."""
        log_dir = Path(self.cfg.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # mirror legacy file naming pattern with start cycle
        log_path = log_dir / f"NAMD_GOMC_started_at_cycle_No_{self.start_cycle}.log"

        # Avoid duplicate handlers if tests instantiate multiple orchestrators, singleton pattern for root logger
        root = logging.getLogger()

        # Ensure root captures INFO from all modules
        if root.level > logging.INFO:
            root.setLevel(logging.INFO)                      
        
        # (Optional) route `warnings.warn()` into logging
        
        logging.captureWarnings(True)
        already = any(isinstance(h, logging.FileHandler) and getattr(h, "_py_mcmd_tag", "") == str(log_path)
                      for h in root.handlers)
        if not already:
            fh = logging.FileHandler(log_path, mode="w")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter("%(message)s"))
            # mark so we don’t re-add
            fh._py_mcmd_tag = str(log_path)
            root.addHandler(fh)

        self._log_path = log_path

    def _emit_start_header(self) -> None:
        start_time = datetime.today()
        
        version = get_version()
        self.logger.info(
            "\n*************************************************\n"
            f"py-MCMD framework version = {version}\n"
            "*************************************************\n"
        )
        msg = (
            "\n*************************************************\n"
            f"date and time (start) = {start_time}\n"
            "\n*************************************************\n"
        )
        self.logger.info(msg)
        # Binary locations (take from engines)
        self.logger.info(
            "\n*************************************************\n"
            f"namd_bin_file = {self.namd.exec_path}\n"
            "\n*************************************************\n"
        )
        self.logger.info(
            "\n*************************************************\n"
            f"gomc_bin_file = {self.gomc.exec_path}\n"
            "\n*************************************************\n"
        )

    def _emit_end_header(self) -> None:
        end_time = datetime.today()
        msg = (
            "\n*************************************************\n"
            f"date and time (end) = {end_time}\n"
            "\n*************************************************\n"
        )
        self.logger.info(msg)
        
    def _prepare_run_dirs(self) -> None:
        """Create NAMD/GOMC root folders; warn if they already exist (stale run risk)."""
        namd_root = self.cfg.path_namd_runs
        gomc_root = self.cfg.path_gomc_runs

        # Mirror the legacy warnings
        if os.path.isdir(namd_root) or os.path.isdir(gomc_root):
            self.logger.warning(
                "\n\tINFORMATION: if the system fails to start (with errors) from the beginning of a simulation, "
                "you may need to delete the main GOMC and NAMD folders. The failure to start/restart may be "
                "caused by the last simulation not finishing correctly."
            )
            self.logger.warning(
                "\n\tINFORMATION: If the system fails to restart a previous run (with errors), you may need to "
                "delete the last subfolders under the main NAMD and GOMC (e.g., NAMD=00000000_a or GOMC=00000001). "
                "The failure to start/restart may be caused by the last simulation not finishing properly."
            )

        # Create roots (respect FIFO decision downstream; keeping GOMC root doesn’t hurt)
        os.makedirs(namd_root, exist_ok=True)
        os.makedirs(gomc_root, exist_ok=True)

        # Optionally store for later usage (e.g., per-cycle dirs)
        self.namd_root = namd_root
        self.gomc_root = gomc_root

    
    # def run(self):
    #     """Run coupled NAMD↔GOMC segments using the legacy-equivalent run_no parity loop."""
    #     self.logger.info("Starting coupled NAMD↔GOMC simulation")

    #     # --- Restart initialization (if starting at cycle > 0) ---
    #     if int(self.cfg.starting_at_cycle_namd_gomc_sims) > 0:
    #         if compute_start_context is not None and apply_start_context is not None:
    #             ctx = compute_start_context(self.cfg, id_width=8)
    #             apply_start_context(self.state, ctx)
    #         else:
    #             # Fallback if restart module is not present
    #             self.state.current_step = (
    #                 (int(self.cfg.namd_run_steps) + int(self.cfg.gomc_run_steps)) * int(self.cfg.starting_at_cycle_namd_gomc_sims)
    #                 + int(self.cfg.namd_minimize_steps)
    #             )

    #         # If PME seeding helper exists, try it (won’t break tests if absent)
    #         if hasattr(self, "refresh_pme_dims_from_run0"):
    #             try:
    #                 self.refresh_pme_dims_from_run0()
    #             except Exception as e:
    #                 self.logger.warning("[PME] refresh_pme_dims_from_run0 failed: %s", e)

    #     starting_sims = int(self.cfg.starting_sims_namd_gomc)
    #     total_sims = int(self.cfg.total_sims_namd_gomc)

    #     cycles_completed = 0

    #     cycle_start_perf = None
    #     self._time_stats_lines = []

    #     for run_no in range(starting_sims, total_sims):
    #         self.logger.info(
    #             "*************************************************\n"
    #             "*************************************************\n"
    #             "run_no = %s (START)\n"
    #             "*************************************************",
    #             run_no,
    #         )

    #         # TIME_STATS: cycle start at even run_no
    #         if run_no % 2 == 0:
    #             cycle_start_perf = time.perf_counter()

    #         if run_no % 2 == 0:
    #             self.namd.run_segment(run_no=run_no, state=self.state)
    #         else:
    #             self.gomc.run_segment(run_no=run_no, state=self.state)
    #             cycles_completed += 1

    #             # TIME_STATS: cycle end at odd run_no
    #             cycle_end_perf = time.perf_counter()
    #             if cycle_start_perf is None:
    #                 cycle_start_perf = cycle_end_perf

    #             cycle_run_time_s = round(cycle_end_perf - cycle_start_perf, 6)

    #             max_namd = float(self.state.timings.max_namd_cycle_time_s or 0.0)
    #             gomc_t = float(self.state.timings.gomc_cycle_time_s or 0.0)
    #             python_only_time_s = round(cycle_run_time_s - (max_namd + gomc_t), 6)

    #             # Header once (first completed cycle)
    #             if run_no == starting_sims + 1:
    #                 header = (
    #                     "*************************************************\n"
    #                     "TIME_STATS_TITLE:\t#Cycle_No\t\tNAMD_time_s\t\t"
    #                     "GOMC_time_s\t\tPython_time_s\t\tTotal_time_s\n"
    #                 )
    #                 self._time_stats_lines.append(header)
    #                 self.logger.info(header.rstrip("\n"))

    #             cycle_no = int(run_no / 2)
    #             data = (
    #                 f"TIME_STATS_DATA:\t{cycle_no}\t\t{max_namd}\t\t{gomc_t}\t\t"
    #                 f"{python_only_time_s}\t\t{cycle_run_time_s}\n"
    #             )
    #             self._time_stats_lines.append(data)
    #             self.logger.info(data.rstrip("\n"))

    #         self.logger.info(
    #             "*************************************************\n"
    #             "run_no = %s (End)\n"
    #             "*************************************************",
    #             run_no,
    #         )

    #     self.logger.info("All cycles completed.")

    #     summary = {
    #         "total_cycles": self.total_cycles,
    #         "start_cycle": self.start_cycle,
    #         "namd_steps": self.namd_steps,
    #         "gomc_steps": self.gomc_steps,
    #         "cycles_completed": cycles_completed,
    #         "total_sims_namd_gomc": self.total_sims_namd_gomc,
    #         "starting_sims_namd_gomc": self.starting_sims_namd_gomc,
    #         "state": self.state.snapshot(),
    #         "time_stats_lines": self._time_stats_lines,
    #     }
    #     self._emit_end_header()
    #     return summary

    def run(self):
        self.logger.info("Starting coupled NAMD↔GOMC simulation")

        if int(self.cfg.starting_at_cycle_namd_gomc_sims) > 0:
            if compute_start_context is not None and apply_start_context is not None:
                ctx = compute_start_context(self.cfg, id_width=10)
                apply_start_context(self.state, ctx)
            else:
                self.state.current_step = (
                    (int(self.cfg.namd_run_steps) + int(self.cfg.gomc_run_steps))
                    * int(self.cfg.starting_at_cycle_namd_gomc_sims)
                    + int(self.cfg.namd_minimize_steps)
                )

            if hasattr(self, "refresh_pme_dims_from_run0"):
                try:
                    self.refresh_pme_dims_from_run0()
                except Exception as e:
                    self.logger.warning("[PME] refresh_pme_dims_from_run0 failed: %s", e)

        starting_sims = int(self.cfg.starting_sims_namd_gomc)
        total_sims = int(self.cfg.total_sims_namd_gomc)

        cycles_completed = 0
        cycle_start_perf = None
        self._time_stats_lines = []

        summary = None

        try:
            for run_no in range(starting_sims, total_sims):
                self.logger.info(
                    "*************************************************\n"
                    "*************************************************\n"
                    "run_no = %s (START)\n"
                    "*************************************************",
                    run_no,
                )

                if run_no % 2 == 0:
                    cycle_start_perf = time.perf_counter()
                    engine_name = "NAMD"
                else:
                    engine_name = "GOMC"

                fifo_resources = self._prepare_fifo_step(engine_name, run_no)

                try:
                    # if run_no % 2 == 0:
                    #     self.namd.run_segment(
                    #         run_no=run_no,
                    #         state=self.state,
                    #         fifo_resources=fifo_resources,
                    #     )
                    # else:
                    #     self.gomc.run_segment(
                    #         run_no=run_no,
                    #         state=self.state,
                    #         fifo_resources=fifo_resources,
                    #     )
                    #     cycles_completed += 1
                    if run_no % 2 == 0:
                        self._call_run_segment(
                            self.namd,
                            run_no=run_no,
                            fifo_resources=fifo_resources,
                        )
                    else:
                        self._call_run_segment(
                            self.gomc,
                            run_no=run_no,
                            fifo_resources=fifo_resources,
                        )
                        cycles_completed += 1

                    self._mark_fifo_step_success(engine_name, run_no)

                except Exception:
                    self._mark_fifo_step_failure(engine_name, run_no)
                    raise

                if run_no % 2 == 1:
                    cycle_end_perf = time.perf_counter()
                    if cycle_start_perf is None:
                        cycle_start_perf = cycle_end_perf

                    cycle_run_time_s = round(cycle_end_perf - cycle_start_perf, 6)

                    max_namd = float(self.state.timings.max_namd_cycle_time_s or 0.0)
                    gomc_t = float(self.state.timings.gomc_cycle_time_s or 0.0)
                    python_only_time_s = round(cycle_run_time_s - (max_namd + gomc_t), 6)

                    if run_no == starting_sims + 1:
                        header = (
                            "*************************************************\n"
                            "TIME_STATS_TITLE:\t#Cycle_No\t\tNAMD_time_s\t\t"
                            "GOMC_time_s\t\tPython_time_s\t\tTotal_time_s\n"
                        )
                        self._time_stats_lines.append(header)
                        self.logger.info(header.rstrip("\n"))

                    cycle_no = int(run_no / 2)
                    data = (
                        f"TIME_STATS_DATA:\t{cycle_no}\t\t{max_namd}\t\t{gomc_t}\t\t"
                        f"{python_only_time_s}\t\t{cycle_run_time_s}\n"
                    )
                    self._time_stats_lines.append(data)
                    self.logger.info(data.rstrip("\n"))

                self.logger.info(
                    "*************************************************\n"
                    "run_no = %s (End)\n"
                    "*************************************************",
                    run_no,
                )

            self.logger.info("All cycles completed.")

            summary = {
                "total_cycles": self.total_cycles,
                "start_cycle": self.start_cycle,
                "namd_steps": self.namd_steps,
                "gomc_steps": self.gomc_steps,
                "cycles_completed": cycles_completed,
                "total_sims_namd_gomc": self.total_sims_namd_gomc,
                "starting_sims_namd_gomc": self.starting_sims_namd_gomc,
                "state": self.state.snapshot(),
                "time_stats_lines": self._time_stats_lines,
            }
            self._emit_end_header()
            return summary

        finally:
            # Graceful teardown on success, failure, or early exit.
            self.fifo_store.cleanup_all()

    def refresh_pme_dims_from_run0(self) -> None:
        """Load NAMD Run-0 PME grid dims into orchestrator state.

        Safe to call at any time. If Run-0 `out.dat` is missing or does not contain
        PME grid dimensions, this leaves existing state unchanged.
        """
        nx0, ny0, nz0, _ = self.namd.get_run0_pme_dims(0)
        if nx0 is not None and ny0 is not None and nz0 is not None:
            self.state.pme_box0 = PmeDims(x=nx0, y=ny0, z=nz0)
            self.logger.info("[PME] Loaded Run-0 PME dims for box0: %s %s %s", nx0, ny0, nz0)
        else:
            self.logger.info("[PME] Run-0 PME dims not available for box0")

        if self.cfg.simulation_type == "GEMC" and (self.cfg.only_use_box_0_for_namd_for_gemc is False):
            nx1, ny1, nz1, _ = self.namd.get_run0_pme_dims(1)
            if nx1 is not None and ny1 is not None and nz1 is not None:
                self.state.pme_box1 = PmeDims(x=nx1, y=ny1, z=nz1)
                self.logger.info("[PME] Loaded Run-0 PME dims for box1: %s %s %s", nx1, ny1, nz1)
            else:
                self.logger.info("[PME] Run-0 PME dims not available for box1")
            
    # FIFO Helpers
    def _fifo_step_id(self, run_no: int) -> str:
        return format_cycle_id(int(run_no), 10)

    def _fifo_dual_write_path(self, engine: str, step_id: str, basename: str) -> Path:
        return Path(self.cfg.log_dir) / "fifo_dual_write" / engine / step_id / basename

    def _prepare_fifo_step(self, engine: str, run_no: int) -> FifoStepResources:
        return self.fifo_store.prepare_step(engine, self._fifo_step_id(run_no))

    def _mark_fifo_step_success(self, engine: str, run_no: int) -> None:
        step_id = self._fifo_step_id(run_no)
        previous_step_id = self._last_successful_fifo_step_by_engine.get(engine)

        self.fifo_store.finalize_step_success(engine, step_id)

        # Retention policy: keep only the most recent successful step per engine.
        if previous_step_id is not None and previous_step_id != step_id:
            self.fifo_store.cleanup_step(engine, previous_step_id)

        self._last_successful_fifo_step_by_engine[engine] = step_id

    def _mark_fifo_step_failure(self, engine: str, run_no: int) -> None:
        self.fifo_store.finalize_step_failure(engine, self._fifo_step_id(run_no))

    def _call_run_segment(self, engine, *, run_no: int, fifo_resources):
        sig = inspect.signature(engine.run_segment)
        kwargs = {
            "run_no": run_no,
            "state": self.state,
        }
        if "fifo_resources" in sig.parameters:
            kwargs["fifo_resources"] = fifo_resources
        return engine.run_segment(**kwargs)