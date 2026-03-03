import os
import logging
from pathlib import Path
from typing import Optional

from engines.base import Engine as BaseEngine
from engines.namd.constants import DEFAULT_NAMD_E_TITLES_LIST
from engines.namd.parser import extract_pme_grid_from_out, find_run0_fft_filename, get_run0_dir
from engines.namd.namd_writer import write_namd_conf_file
from engines.namd.energy import get_namd_energy_data
from engines.namd.energy_compare import compare_namd_gomc_energies

from utils.path import format_cycle_id
from utils.subprocess_runner import Command, SubprocessRunner
from orchestrator.state import RunState

logger = logging.getLogger(__name__)
# from __future__ import annotations

# import os
# import logging
# from datetime import datetime
# from pathlib import Path
# from typing import Optional
# from engines.base import Engine as BaseEngine
# from engines.namd.constants import DEFAULT_NAMD_E_TITLES_LIST
# from engines.namd.energy import get_namd_energy_data
# from engines.namd.energy_compare import compare_namd_gomc_energies
# from engines.namd.namd_writer import write_namd_conf_file
# # from run_NAMD_GOMC_refactored import get_namd_run_0_fft_filename
# from py_mcmd_refactored.tests.test_namd_energy_compare import cfg
# from utils.path import format_cycle_id
# from engines.namd.parser import extract_pme_grid_from_out
# from engines.namd.parser import find_run0_fft_filename
# from engines.namd.parser import get_run0_dir
# from pathlib import Path
# from typing import Callable, Optional, Tuple
# from utils.subprocess_runner import Command, SubprocessRunner
from engines.namd.plan import NamdExecutionPlan, build_namd_execution_plan

logger = logging.getLogger(__name__)
class NamdEngine(BaseEngine):
    # def __init__(self, cfg, engine_type="NAMD", dry_run: bool = False):
    #     super().__init__(cfg, engine_type)
    #     self.dry_run = dry_run

    #     # runner is required for end-to-end segment execution
    #     self.runner = SubprocessRunner(dry_run=self.dry_run)

    #     self.bin_dir = Path(cfg.namd2_bin_directory)


    #     self.path_template = Path(cfg.path_namd_template) if cfg.path_namd_template else None
    #     if self.bin_dir.exists():
    #         self.exec_path = self.bin_dir / "namd2"
    #         # self.exec_path= "{}/{}/{}".format(
    #         #     str(os.getcwd()),
    #         #     self.bin_dir,
    #         #     "namd2"
    #         #     )
    #     else:
    #         if self.dry_run:
    #             logger.warning("NAMD bin dir %s not found; continuing in dry_run.", self.bin_dir)
    #             # self.exec_path = self.bin_dir / "namd2"  # placeholder
    #             self.exec_path = "namd2"
    #         else:
    #             raise FileNotFoundError(f"NAMD binary directory {self.bin_dir} does not exist.")
            
    #     # ... use namd_template when generating the per-cycle NAMD input ...
        
    #     # self.run_steps = int(getattr(cfg, "namd_run_steps", 0))
    #     self.runner = SubprocessRunner(dry_run=self.dry_run)
    #     self.steps_per_run = int(getattr(cfg, "namd_run_steps", 0))


    # def run(self):
    #     # Implement the logic to run NAMD simulation using the template
    #     pass


    def __init__(self, cfg, engine_type="NAMD", dry_run: bool = False):
        super().__init__(cfg, engine_type, dry_run=dry_run)
        self.dry_run = dry_run

        self.bin_dir = Path(cfg.namd2_bin_directory)
        self.path_template = Path(cfg.path_namd_template) if cfg.path_namd_template else None

        if self.bin_dir.exists():
            self.exec_path = str((self.bin_dir / "namd2").resolve())
        else:
            if self.dry_run:
                logger.warning("NAMD bin dir %s not found; continuing in dry_run.", self.bin_dir)
                self.exec_path = "namd2"
            else:
                raise FileNotFoundError(f"NAMD binary directory {self.bin_dir} does not exist.")

        # IMPORTANT: do NOT use `self.run_steps` as an int (it must remain callable)
        self.steps_per_run = int(getattr(cfg, "namd_run_steps", 0))

        # subprocess adapter
        self.runner = SubprocessRunner(dry_run=self.dry_run)

    def run(self):
        raise NotImplementedError("Use NamdEngine.run_segment(...) instead.")
    # -------------------------------------------------------------------------
    # Run-0 PME helpers
    # -------------------------------------------------------------------------
    def get_run0_pme_dims(self, box_number: int)-> tuple[Optional[int], Optional[int], Optional[int], str]:
        """
        Returns (nx, ny, nz, run0_dir_path) for the given box (0 or 1).
        Never raises on missing files; returns (None, None, None, run0_dir_path).
        """
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError("box_number must be integer 0 or 1")

        # Run 0 directory name (zero-padded run id + suffix a/b)
        run0_id = format_cycle_id(0) # default width in utils.path is 10
        suffix = "a" if box_number == 0 else "b"
        run0_dir = Path(self.cfg.path_namd_runs) / f"{run0_id}_{suffix}"

        out_path = run0_dir / "out.dat"
        nx, ny, nz = extract_pme_grid_from_out(out_path)

        if nx is None:
            logger.warning("[NAMD] PME grid not found in %s (box=%s)", out_path, box_number)

        return nx, ny, nz, str(run0_dir)
    
    # -------------------------------------------------------------------------
    # Run-0 FFT helpers (with 10-digit→8-digit fallback)
    # -------------------------------------------------------------------------
    # def get_run0_fft_filename(self, box_number: int) -> tuple[Optional[str], str]:
        # """
        # Returns (fft_filename or None, run0_dir_path_str) for box_number ∈ {0, 1}.
        # Never raises for missing dir/file; logs a warning and returns (None, dir).
        # """
        # if not isinstance(box_number, int) or box_number not in (0, 1):
        #     raise ValueError("box_number must be integer 0 or 1")
        # # Prefer 10-digit run0 dir (matches PME test), fallback to 8-digit (matches older FFT tests)
        # for width in (10, 8):
        #     run0_dir = get_run0_dir(Path(self.cfg.path_namd_runs), box_number, id_width=width)
        #     try:
        #         # Reuse your existing helper already in this module:
        #         fft_name = find_run0_fft_filename(run0_dir)
        #         return fft_name, str(run0_dir)
        #     except FileNotFoundError:
        #         continue
        # # if neither exists, mirror legacy-like behavior by raising
        # raise FileNotFoundError("Run-0 directory does not exist for FFT lookup.")
        # # if fft_name is None:
        # #     logger.warning("[NAMD] FFTW plan file not detected in run0 dir %s (box=%s)", run0_dir, box_number)
    
    def get_run0_fft_filename(self, box_number: int) -> tuple[Optional[str], str]:
        """
        Returns (fft_filename or None, run0_dir_path_str) for box_number ∈ {0, 1}.

        Behavior (matches existing unit tests):
        - If run0 directory exists (8-digit or 10-digit), return:
            - (filename, dir) if a file starting with 'FFTW_NAMD' exists
            - (None, dir) if no matching file exists
        - If neither 8-digit nor 10-digit run0 dir exists, raise FileNotFoundError.
        """
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError("box_number must be integer 0 or 1")

        # IMPORTANT: existing tests create 8-digit dirs (00000000_a), so try 8 first.
        widths_to_try = (8, 10)

        for width in widths_to_try:
            run0_dir = get_run0_dir(Path(self.cfg.path_namd_runs), box_number, id_width=width)

            if not run0_dir.exists():
                continue  # try next width

            # Directory exists -> safe to call finder (which raises if dir missing)
            fft_name = find_run0_fft_filename(run0_dir)

            if fft_name is None:
                logger.warning(
                    "[NAMD] FFTW plan file not detected in run0 dir %s (box=%s)",
                    run0_dir,
                    box_number,
                )
            return fft_name, str(run0_dir)

        # Neither width exists -> keep test behavior for missing run0 dir
        base = Path(self.cfg.path_namd_runs)
        suffix = "a" if box_number == 0 else "b"
        raise FileNotFoundError(
            f"Run-0 directory not found for box={box_number}. Tried: "
            f"{base}/00000000_{suffix} and {base}/0000000000_{suffix}"
        )


        

    def delete_namd_run_0_fft_file(self, box_number: int) -> None:
        """
        Deletes the run 0 (1st NAMD simulation) FFT filename.

        Parameters
        ----------
        box_number : int
            The simulation box number, which can only be 0 or 1
        """
        # Preserve legacy error message text, but modernize validation
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError(
                "ERROR Enter an interger of 0 or 1  for box_number in "
                "the get_namd_run_0_pme_dim function. \n"
            )

        write_log_data = (
            "*************************************************\n"
            "The NAMD FFT file was deleted from Run 0 in Box {} \n"
            "************************************************* \n".format(str(box_number))
        )

        try:
            # Use the parser to locate the FFT file and directory
            fft_filename, run0_dir = self.get_run0_fft_filename(
                box_number=box_number
            )

            # If we found a filename, delete it. Mirror legacy: swallow errors.
            if fft_filename:
                fft_path = Path(run0_dir) / fft_filename
                try:
                    # Python 3.8+: missing_ok available
                    fft_path.unlink(missing_ok=True)  # type: ignore[arg-type]
                except TypeError:
                    # Fallback for Python < 3.8
                    try:
                        fft_path.unlink()
                    except FileNotFoundError:
                        pass

            # Log/print banner regardless of outcome (legacy parity)
            logger.info(write_log_data.strip("\n"))
            print(write_log_data)

        except Exception:
            # Legacy behavior: still emit the banner even if something goes wrong
            logger.info(write_log_data.strip("\n"))
            print(write_log_data)

    
    # from engines.namd.energy_compare import compare_namd_gomc_energies

    # # inside your engine method:
    # compare_namd_gomc_energies(
    #     self.cfg,  # SimulationConfig
    #     pot_final, pot_initial,
    #     vpe_final, vpe_initial,
    #     run_no, box_number,
    # )

    def run_steps(self, *, run_dir: Path, cores: int) -> int:
        cmd = Command(
            argv=[str(self.exec_path), f"+p{int(cores)}", "in.conf"],
            cwd=Path(run_dir),
            stdout_path=Path(run_dir) / "out.dat",
        )
        return self.runner.run_and_wait(cmd)
    
    def link_run0_fft_file_into_dir(self, box_number: int, dest_dir: Path) -> None:
        """Link (symlink) the Run-0 FFTW plan file into a later NAMD run directory.

        Legacy behavior used: `ln -sf <run0_dir>/<fft_file> <dest_dir>` which creates/overwrites
        a symlink inside `dest_dir`.

        - If the Run-0 FFT file is not found, this is a no-op (with a warning).
        - If the destination already exists (file/symlink), it is replaced.
        """
        if not isinstance(box_number, int) or box_number not in (0, 1):
            raise ValueError("box_number must be integer 0 or 1")

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        fft_filename, run0_dir = self.get_run0_fft_filename(box_number)
        if not fft_filename:
            logger.warning(
                "[NAMD] Cannot link run0 FFT file: none detected for box=%s (run0_dir=%s)",
                box_number,
                run0_dir,
            )
            return

        src = Path(run0_dir) / fft_filename
        dst = dest_dir / fft_filename

        # Mirror `ln -sf`: remove existing destination entry if present.
        try:
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
        except FileNotFoundError:
            pass

        if dst.exists() and dst.is_dir():
            raise IsADirectoryError(f"Destination path {dst} is a directory; cannot overwrite with symlink")

        # If source is missing, raise unless dry_run (then create a placeholder).
        if not src.exists():
            if self.dry_run:
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_text("[dry_run] missing FFTW plan placeholder\n")
            else:
                raise FileNotFoundError(f"Run-0 FFT file not found: {src}")

        dst.symlink_to(src)
        logger.info("[NAMD] Linked run0 FFT file for box=%s: %s -> %s", box_number, dst, src)

    def build_execution_plan(self, *, box0_dir: Path, box1_dir: Optional[Path]) -> NamdExecutionPlan:
        exec_path = str(self.exec_path) if self.exec_path is not None else "namd2"
        return build_namd_execution_plan(
            self.cfg,
            exec_path=exec_path,
            box0_dir=Path(box0_dir),
            box1_dir=Path(box1_dir) if box1_dir is not None else None,
        )


    def execute_plan(self, plan: NamdExecutionPlan) -> dict:
        """Execute the plan with legacy wait semantics.

        - series: start+wait box0, then start+wait box1
        - parallel: start box0, start box1, then wait box0, wait box1
        """
        if plan.mode == "series" or plan.box1 is None:
            h0 = self.runner.start(plan.box0)
            rc0 = self.runner.wait(h0)
            rc1 = None
            if plan.box1 is not None:
                h1 = self.runner.start(plan.box1)
                rc1 = self.runner.wait(h1)
            return {"rc_box0": rc0, "rc_box1": rc1, "mode": plan.mode}

        # parallel
        h0 = self.runner.start(plan.box0)
        h1 = self.runner.start(plan.box1)
        rc0 = self.runner.wait(h0)
        rc1 = self.runner.wait(h1)
        return {"rc_box0": rc0, "rc_box1": rc1, "mode": plan.mode}
    
    # -------------------------------------------------------------------------
    # NAMD phase end-to-end (even run_no)
    # -------------------------------------------------------------------------
    def _two_box_enabled(self) -> bool:
        return (self.cfg.simulation_type == "GEMC") and (self.cfg.only_use_box_0_for_namd_for_gemc is False)


    def run_segment(self, *, run_no: int, state: RunState) -> dict:
        """Run the full NAMD segment for an even run_no and update RunState."""
        if int(run_no) % 2 != 0:
            raise ValueError(f"NAMD segment must be called for even run_no; got run_no={run_no}")

        box0 = 0
        box1 = 1
        two_box = self._two_box_enabled()

        gomc_newdir = str(state.gomc_dir) if state.gomc_dir is not None else "NA"

        # 1) Write NAMD config(s)
        python_file_directory = Path.cwd()

        namd_box0_dir = write_namd_conf_file(
            python_file_directory,
            self.cfg.path_namd_template,
            self.cfg.path_namd_runs,
            gomc_newdir,
            run_no,
            box0,
            self.cfg.namd_run_steps,
            self.cfg.namd_minimize_steps,
            self.cfg.namd_rst_dcd_xst_steps,
            self.cfg.namd_console_blkavg_e_and_p_steps,
            self.cfg.simulation_temp_k,
            self.cfg.simulation_pressure_bar,
            self.cfg.starting_pdb_box_0_file,
            self.cfg.starting_psf_box_0_file,
            state.pme_box0.x, state.pme_box0.y, state.pme_box0.z,
            set_x_dim=self.cfg.set_dims_box_0_list[0],
            set_y_dim=self.cfg.set_dims_box_0_list[1],
            set_z_dim=self.cfg.set_dims_box_0_list[2],
        )
        state.namd_box0_dir = Path(namd_box0_dir)

        namd_box1_dir: Optional[str] = None
        if two_box:
            namd_box1_dir = write_namd_conf_file(
                python_file_directory,
                self.cfg.path_namd_template,
                self.cfg.path_namd_runs,
                gomc_newdir,
                run_no,
                box1,
                self.cfg.namd_run_steps,
                self.cfg.namd_minimize_steps,
                self.cfg.namd_rst_dcd_xst_steps,
                self.cfg.namd_console_blkavg_e_and_p_steps,
                self.cfg.simulation_temp_k,
                self.cfg.simulation_pressure_bar,
                self.cfg.starting_pdb_box_1_file,
                self.cfg.starting_psf_box_1_file,
                state.pme_box1.x, state.pme_box1.y, state.pme_box1.z,
                set_x_dim=self.cfg.set_dims_box_1_list[0],
                set_y_dim=self.cfg.set_dims_box_1_list[1],
                set_z_dim=self.cfg.set_dims_box_1_list[2],
                fft_add_namd_ang_to_box_dim=0,
            )
            state.namd_box1_dir = Path(namd_box1_dir)

        # 2) FFT housekeeping
        if run_no == 0:
            self.delete_namd_run_0_fft_file(box0)
            if two_box:
                self.delete_namd_run_0_fft_file(box1)
        else:
            self.link_run0_fft_file_into_dir(box0, Path(namd_box0_dir))
            if two_box and namd_box1_dir is not None:
                self.link_run0_fft_file_into_dir(box1, Path(namd_box1_dir))

        # 3) Execute NAMD with legacy series/parallel semantics
        mode = self.cfg.namd_simulation_order if two_box else "series"

        cores0 = int(self.cfg.total_no_cores) if (not two_box or mode == "series") else int(self.cfg.no_core_box_0)
        cmd0 = Command(
            argv=[str(self.exec_path), f"+p{cores0}", "in.conf"],
            cwd=Path(namd_box0_dir),
            stdout_path=Path(namd_box0_dir) / "out.dat",
        )

        cmd1: Optional[Command] = None
        if two_box and namd_box1_dir is not None:
            cores1 = int(self.cfg.total_no_cores) if mode == "series" else int(self.cfg.no_core_box_1)
            cmd1 = Command(
                argv=[str(self.exec_path), f"+p{cores1}", "in.conf"],
                cwd=Path(namd_box1_dir),
                stdout_path=Path(namd_box1_dir) / "out.dat",
            )

        rc0 = rc1 = None
        if cmd1 is None or mode == "series":
            h0 = self.runner.start(cmd0)
            rc0 = self.runner.wait(h0)
            if cmd1 is not None:
                h1 = self.runner.start(cmd1)
                rc1 = self.runner.wait(h1)
        else:
            h0 = self.runner.start(cmd0)
            h1 = self.runner.start(cmd1)
            rc0 = self.runner.wait(h0)
            rc1 = self.runner.wait(h1)

        if (rc0 not in (None, 0)) or (rc1 not in (None, 0)):
            if not self.dry_run:
                raise RuntimeError(f"NAMD failed (rc0={rc0}, rc1={rc1}, mode={mode})")

        # 4) Parse energies -> cache in state
        def _parse_to_energy(run_dir: Path, energy_obj) -> None:
            lines = (run_dir / "out.dat").read_text(errors="ignore").splitlines(True)
            (
                _elect_series,
                _elect_initial,
                _elect_final,
                _pot_series,
                pot_initial,
                pot_final,
                _vpe_series,
                vpe_initial,
                vpe_final,
            ) = get_namd_energy_data(lines, DEFAULT_NAMD_E_TITLES_LIST)
            energy_obj.namd_potential_initial = pot_initial
            energy_obj.namd_potential_final = pot_final
            energy_obj.namd_vdw_plus_elec_initial = vpe_initial
            energy_obj.namd_vdw_plus_elec_final = vpe_final

        try:
            _parse_to_energy(Path(namd_box0_dir), state.energy_box0)
        except Exception as e:
            if self.dry_run:
                logger.warning("[NAMD] Energy parse failed for box0 (dry_run): %s", e)
            else:
                raise

        if two_box and namd_box1_dir is not None:
            try:
                _parse_to_energy(Path(namd_box1_dir), state.energy_box1)
            except Exception as e:
                if self.dry_run:
                    logger.warning("[NAMD] Energy parse failed for box1 (dry_run): %s", e)
                else:
                    raise

        # 5) Continuity check (GOMC -> NAMD) when applicable
        if (run_no != 0) and (run_no != int(self.cfg.starting_sims_namd_gomc)):
            e0 = state.energy_box0
            if (e0.gomc_potential_final is not None) and (e0.namd_potential_initial is not None) and (
                e0.gomc_vdw_plus_elec_final is not None
            ) and (e0.namd_vdw_plus_elec_initial is not None):
                compare_namd_gomc_energies(
                    self.cfg,
                    e0.gomc_potential_final,
                    e0.namd_potential_initial,
                    e0.gomc_vdw_plus_elec_final,
                    e0.namd_vdw_plus_elec_initial,
                    run_no,
                    0,
                )

            if two_box:
                e1 = state.energy_box1
                if (e1.gomc_potential_final is not None) and (e1.namd_potential_initial is not None) and (
                    e1.gomc_vdw_plus_elec_final is not None
                ) and (e1.namd_vdw_plus_elec_initial is not None):
                    compare_namd_gomc_energies(
                        self.cfg,
                        e1.gomc_potential_final,
                        e1.namd_potential_initial,
                        e1.gomc_vdw_plus_elec_final,
                        e1.namd_vdw_plus_elec_initial,
                        run_no,
                        1,
                    )

        # 6) Update PME dims after Run-0 (out.dat exists now)
        if run_no == 0:
            nx0, ny0, nz0, _ = self.get_run0_pme_dims(0)
            if (nx0 is not None) and (ny0 is not None) and (nz0 is not None):
                state.pme_box0.x, state.pme_box0.y, state.pme_box0.z = int(nx0), int(ny0), int(nz0)
            if two_box:
                nx1, ny1, nz1, _ = self.get_run0_pme_dims(1)
                if (nx1 is not None) and (ny1 is not None) and (nz1 is not None):
                    state.pme_box1.x, state.pme_box1.y, state.pme_box1.z = int(nx1), int(ny1), int(nz1)

        # 7) Update step counter (legacy rule)
        if run_no == 0:
            state.current_step += int(self.cfg.namd_run_steps) + int(self.cfg.namd_minimize_steps)
        else:
            state.current_step += int(self.cfg.namd_run_steps)

        return {
            "run_no": int(run_no),
            "mode": mode,
            "rc_box0": rc0,
            "rc_box1": rc1,
            "namd_box0_dir": str(namd_box0_dir),
            "namd_box1_dir": str(namd_box1_dir) if namd_box1_dir is not None else None,
        }
