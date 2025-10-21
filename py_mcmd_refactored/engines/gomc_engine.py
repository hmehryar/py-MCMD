import os
import logging
from pathlib import Path
from engines.base import Engine as BaseEngine

logger = logging.getLogger(__name__)
class GomcEngine(BaseEngine):
    def __init__(self, cfg, engine_type: str="GOMC", dry_run: bool = False):
        super().__init__(cfg, engine_type)

        self.dry_run = dry_run
        # gomc_bin_directory is optional during tests / dry-run
        self.bin_dir = Path(cfg.gomc_bin_directory)
        self.path_template = Path(cfg.path_gomc_template) if getattr(cfg, "path_gomc_template", None) else None

        # self.path_template: Path = Path(cfg.path_gomc_template) if cfg.path_gomc_template else None
        self.use_gpu: bool = str(cfg.gomc_use_CPU_or_GPU).upper() == "GPU"
        self.ensemble: str = str(cfg.simulation_type).upper()
        self.exec_name: str = f"GOMC_{'GPU' if self.use_gpu else 'CPU'}_{self.ensemble}"


        # In dry-run, don't touch the filesystem; tests may not provide real binaries.
        if not self.dry_run:
            if self.bin_dir is None or not self.bin_dir.exists():
                raise FileNotFoundError(
                    f"[GOMC] Binary directory not found: {self.bin_dir!r}"
                )
            if self.exec_path is None or not self.exec_path.exists():
                raise FileNotFoundError(
                    f"[GOMC] Executable not found: {self.exec_name} under {self.bin_dir}"
                )
            # self.exec_path = self.bin_dir / exe
            self.exec_path = "{}/{}/GOMC_{}_{}".format(
                str(os.getcwd()),
                self.bin_dir,
                self.exec_name
            )
        else:
             logger.warning("GOMC binary dir %s not found; continuing in dry_run.", self.bin_dir)
        self.run_steps = int(getattr(cfg, "gomc_run_steps", 0))    
        # ... use gomc_template when generating the per-cycle GOMC input ...
    def run(self):
        # Implement the logic to run GOMC simulation using the template
        pass