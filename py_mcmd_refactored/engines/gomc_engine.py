import os
import logging
from pathlib import Path
from engines.base import Engine as BaseEngine

logger = logging.getLogger(__name__)
class GomcEngine(BaseEngine):
    def __init__(self, cfg, engine_type="GOMC"):
        super().__init__(cfg, engine_type)
        
        self.bin_dir = Path(cfg.gomc_bin_directory)
        self.path_template = Path(cfg.path_gomc_template) if cfg.path_gomc_template else None
        self.use_gpu = str(cfg.gomc_use_CPU_or_GPU).upper() == "GPU"
        self.ensemble = str(cfg.simulation_type).upper()
        exe = f"GOMC_{'GPU' if self.use_gpu else 'CPU'}_{self.ensemble}"
        if self.bin_dir.exists():
            # self.exec_path = self.bin_dir / exe
            self.exec_path = "{}/{}/GOMC_{}_{}".format(
                str(os.getcwd()),
                self.bin_dir,
                'GPU' if self.use_gpu else 'CPU',
                self.ensemble,
            )
        else:
            raise FileNotFoundError(f"GOMC binary directory {self.bin_dir} does not exist.")
        # ... use gomc_template when generating the per-cycle GOMC input ...
    def run(self):
        # Implement the logic to run GOMC simulation using the template
        pass