import os
import logging
from pathlib import Path
from config.models import SimulationConfig

logger = logging.getLogger(__name__)

class Engine:
    """Abstract base for NAMD and GOMC engines."""

    def __init__(self, cfg: SimulationConfig, engine_type: str, dry_run: bool = False):
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
        self.dry_run: bool = dry_run
        # Paths for this engine’s runs
        self.run_dir: Path = Path(self.engine_type)
        os.makedirs(self.run_dir, exist_ok=True)

        # Emit warnings if folders already exist
        if self.run_dir.exists() and any(self.run_dir.iterdir()):
            logger.warning(
                f"[{self.engine_type}] Directory {self.run_dir} already exists. "
                "If startup/restart fails, try deleting it or its last subfolders."
            )

        self.bin_dir: Path | None = None
        self.exec_path: Path | None = None
        self.path_template: Path | None = None
        # Binary path
        # if self.engine_type == "NAMD":
        #     self.bin_dir = Path(cfg.namd2_bin_directory)
        #     self.path_template = Path(cfg.path_namd_template) if cfg.path_namd_template else None
        #     if self.bin_dir.exists():
        #         self.exec_path = self.bin_dir / "namd2"
        #     else:
        #         raise FileNotFoundError(f"NAMD binary directory {self.bin_dir} does not exist.")
        # elif self.engine_type == "GOMC":
        #     self.bin_dir = Path(cfg.gomc_bin_directory)
        #     self.path_template = Path(cfg.path_gomc_template) if cfg.path_gomc_template else None
        #     if self.bin_dir.exists():
        #         self.exec_path = "{}/{}/GOMC_{}_{}".format(
        #             str(os.getcwd()),
        #             self.bin_dir,
        #             self.cfg.gomc_use_CPU_or_GPU,
        #             self.cfg.simulation_type,
        #         )
        #     else:
        #         raise FileNotFoundError(f"GOMC binary directory {self.bin_dir} does not exist.")
        # else:
        #     raise ValueError(f"Unknown engine_type {engine_type}")
        if self.engine_type not in ("NAMD", "GOMC"):
            raise ValueError(f"Unknown engine_type {self.engine_type}")

        logger.info(
            f"\n\t[{self.engine_type}] initialized with\n\t\trun_dir={self.run_dir},\n\t\tbin_dir={self.bin_dir},\n\t\tpath_template={self.path_template}"
        )

    def run(self):
        raise NotImplementedError("Subclasses must implement run()")
