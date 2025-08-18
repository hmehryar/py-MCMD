# orchestrator/manager.py
import os
import logging
from config.models import SimulationConfig
# you’ll wire in your engines once they exist:
# from engines.namd_engine import NAMDEngine
# from engines.gomc_engine import GOMCEngine
from engines.base import Engine
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

        self.namd = Engine(cfg, "NAMD")
        self.gomc = Engine(cfg, "GOMC")

        self.total_cycles = int(getattr(cfg, "total_cycles_namd_gomc_sims", 0))
        self.start_cycle = int(getattr(cfg, "starting_at_cycle_namd_gomc_sims", 0))
        self.namd_steps  = int(getattr(cfg, "namd_run_steps", 0))
        self.gomc_steps  = int(getattr(cfg, "gomc_run_steps", 0))

        if self.total_cycles <= 0:
            raise ValueError("total_cycles_namd_gomc_sims must be > 0")

        # NEW: ensure run directories exist (and warn if stale)
        self._prepare_run_dirs()

        logger.info(
            "Initialized orchestrator: total_cycles=%s, start_cycle=%s, namd_steps=%s, gomc_steps=%s, dry_run=%s",
            self.total_cycles, self.start_cycle, self.namd_steps, self.gomc_steps, self.dry_run
        )
    def _prepare_run_dirs(self) -> None:
        """Create NAMD/GOMC root folders; warn if they already exist (stale run risk)."""
        namd_root = self.cfg.path_namd_runs
        gomc_root = self.cfg.path_gomc_runs

        # Mirror the legacy warnings
        if os.path.isdir(namd_root) or os.path.isdir(gomc_root):
            logger.warning(
                "INFORMATION: if the system fails to start (with errors) from the beginning of a simulation, "
                "you may need to delete the main GOMC and NAMD folders. The failure to start/restart may be "
                "caused by the last simulation not finishing correctly."
            )
            logger.warning(
                "INFORMATION: If the system fails to restart a previous run (with errors), you may need to "
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
