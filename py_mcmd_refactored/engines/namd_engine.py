import os
import logging
from pathlib import Path
from typing import Optional
from engines.base import Engine as BaseEngine
from engines.namd.constants import DEFAULT_NAMD_E_TITLES_LIST
from utils.path import format_cycle_id
from engines.namd.parser import extract_pme_grid_from_out
from engines.namd.parser import find_run0_fft_filename


logger = logging.getLogger(__name__)
class NamdEngine(BaseEngine):
    def __init__(self, cfg, engine_type="NAMD", dry_run: bool = False):
        super().__init__(cfg, engine_type)
        self.dry_run = dry_run

        self.bin_dir = Path(cfg.namd2_bin_directory)


        self.path_template = Path(cfg.path_namd_template) if cfg.path_namd_template else None
        if self.bin_dir.exists():
            self.exec_path = self.bin_dir / "namd2"
            self.exec_path= "{}/{}/{}".format(
                str(os.getcwd()),
                self.bin_dir,
                "namd2"
                )
        else:
            if self.dry_run:
                logger.warning("NAMD bin dir %s not found; continuing in dry_run.", self.bin_dir)
                # self.exec_path = self.bin_dir / "namd2"  # placeholder
            else:
                raise FileNotFoundError(f"NAMD binary directory {self.bin_dir} does not exist.")
            
        # ... use namd_template when generating the per-cycle NAMD input ...
        
        self.run_steps = int(getattr(cfg, "namd_run_steps", 0))
    def run(self):
        # Implement the logic to run NAMD simulation using the template
        pass

    def get_run0_pme_dims(self, box_number: int):
        """
        Returns (nx, ny, nz, run0_dir_path) for the given box (0 or 1).
        Never raises on missing files; returns (None, None, None, run0_dir_path).
        """
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError("box_number must be integer 0 or 1")

        # Run 0 directory name (zero-padded run id + suffix a/b)
        run0_id = format_cycle_id(0)
        suffix = "a" if box_number == 0 else "b"
        run0_dir = Path(self.cfg.path_namd_runs) / f"{run0_id}_{suffix}"

        out_path = run0_dir / "out.dat"
        nx, ny, nz = extract_pme_grid_from_out(out_path)

        if nx is None:
            logger.warning("[NAMD] PME grid not found in %s (box=%s)", out_path, box_number)

        return nx, ny, nz, str(run0_dir)
    
    def get_run0_fft_filename(self, box_number: int) -> tuple[Optional[str], str]:
        """
        Returns (fft_filename or None, run0_dir_path_str) for box_number ∈ {0, 1}.
        Never raises for missing dir/file; logs a warning and returns (None, dir).
        """
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError("box_number must be integer 0 or 1")

        run0_id = format_cycle_id(0, 8)  # or 10, depending on your project-wide choice
        suffix = "a" if box_number == 0 else "b"
        run0_dir = Path(self.cfg.path_namd_runs) / f"{run0_id}_{suffix}"

        fft_name = find_run0_fft_filename(run0_dir)
        if fft_name is None:
            logger.warning("[NAMD] FFTW plan file not detected in run0 dir %s (box=%s)", run0_dir, box_number)

        return fft_name, str(run0_dir)