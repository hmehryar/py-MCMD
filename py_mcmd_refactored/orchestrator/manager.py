# orchestrator/manager.py

import logging
from config.models import SimulationConfig
# you’ll wire in your engines once they exist:
# from engines.namd_engine import NAMDEngine
# from engines.gomc_engine import GOMCEngine

class SimulationOrchestrator:
    def __init__(self, cfg: SimulationConfig):
        self.cfg = cfg
        self.logger = logging.getLogger(self.__class__.__name__)
        # instantiate your engine wrappers here:
        # self.namd = NAMDEngine(cfg)
        # self.gomc = GOMCEngine(cfg)

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
