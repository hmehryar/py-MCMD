import os
import logging
from pathlib import Path
from config.models import SimulationConfig

logger = logging.getLogger(__name__)

class Engine:
    """Abstract base for NAMD and GOMC engines."""

    def __init__(self, cfg: SimulationConfig, engine_type: str):
        """
        Parameters
        ----------
        cfg : SimulationConfig
            The simulation configuration object.
        engine_type : str
            Either "NAMD" or "GOMC".
        """
        self.cfg = cfg
        self.engine_type = engine_type.upper()

        # Paths for this engine’s runs
        self.run_dir = Path(self.engine_type)
        os.makedirs(self.run_dir, exist_ok=True)

        # Emit warnings if folders already exist
        if self.run_dir.exists() and any(self.run_dir.iterdir()):
            logger.warning(
                f"[{self.engine_type}] Directory {self.run_dir} already exists. "
                "If startup/restart fails, try deleting it or its last subfolders."
            )

        # Binary path
        if self.engine_type == "NAMD":
            self.bin_dir = Path(cfg.namd2_bin_directory)
        elif self.engine_type == "GOMC":
            self.bin_dir = Path(cfg.gomc_bin_directory)
        else:
            raise ValueError(f"Unknown engine_type {engine_type}")

        logger.info(
            f"[{self.engine_type}] initialized with run_dir={self.run_dir}, bin_dir={self.bin_dir}"
        )

    def run(self):
        raise NotImplementedError("Subclasses must implement run()")
