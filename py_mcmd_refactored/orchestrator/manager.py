# orchestrator/manager.py
import os
import logging
from datetime import datetime
from pathlib import Path

from utils.path import format_cycle_id
from config.models import SimulationConfig
# you’ll wire in your engines once they exist:
# from engines.namd_engine import NAMDEngine
# from engines.gomc_engine import GOMCEngine
from engines.base import Engine
from engines.gomc_engine import GomcEngine
from engines.namd_engine import NamdEngine
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

        self.dry_run = dry_run

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
            "Initialized orchestrator: total_cycles=%s, start_cycle=%s, namd_steps=%s, gomc_steps=%s, dry_run=%s, total_sims=%, start_sims=%s",
            self.total_cycles, self.start_cycle, self.namd_steps, self.gomc_steps, self.dry_run, self.total_sims_namd_gomc, self.starting_sims_namd_gomc
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
    def run(self):
        """High-level entrypoint for running all cycles."""
        self.logger.info("Starting coupled NAMD↔GOMC simulation")
        start = self.cfg.starting_at_cycle_namd_gomc_sims
        end   = self.cfg.total_cycles_namd_gomc_sims

        for cycle in range(start, end):
            self.logger.debug(f"Cycle {cycle+1}/{end}")
            cid = format_cycle_id(cycle, 8)  # or 10 if you prefer 10-digit folders
            namd_cycle_dir = Path(self.namd_root) / f"{cid}_a"
            gomc_cycle_dir = Path(self.gomc_root) / cid

            self.logger.info(f"Preparing directories for cycle {cycle}: {cid}, {namd_cycle_dir} and {gomc_cycle_dir}")
            namd_cycle_dir.mkdir(parents=True, exist_ok=True)
            gomc_cycle_dir.mkdir(parents=True, exist_ok=True)
            # --- NAMDEngine step ---
            # self.namd.prepare(cycle)
            # self.namd.run_cycle(cycle)
            # result_namd = self.namd.collect_results(cycle)

            # --- GOMCEngine step ---
            # self.gomc.prepare(cycle)
            # self.gomc.run_cycle(cycle)
            # result_gomc = self.gomc.collect_results(cycle)

            # optionally combine or log the per-cycle stats
            # self.logger.info(f"Cycle {cycle} complete")

        self.logger.info("All cycles completed.")
        summary = {
            "total_cycles": self.total_cycles,
            "start_cycle": self.start_cycle,
            "namd_steps": self.namd_steps,
            "gomc_steps": self.gomc_steps,
            "cycles_completed": 0,
            "total_sims_namd_gomc": self.total_sims_namd_gomc,
            "starting_sims_namd_gomc": self.starting_sims_namd_gomc,
        }
        return summary
