# py_mcmd_refactored/engines/gomc/gomc_writer.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
import logging
import os

from py_mcmd_refactored.config.models import SimulationConfig
from py_mcmd_refactored.utils.path import format_cycle_id

log = logging.getLogger(__name__)

# ----------------------------- DTOs -----------------------------

@dataclass(frozen=True)
class GOMCStartFiles:
    starting_pdb_box_0_file: Path
    starting_pdb_box_1_file: Path
    starting_psf_box_0_file: Path
    starting_psf_box_1_file: Path


@dataclass(frozen=True)
class GOMCSimParams:
    gomc_run_steps: int
    gomc_rst_coor_ckpoint_steps: int
    gomc_console_blkavg_hist_steps: int
    gomc_hist_sample_steps: int
    simulation_temp_k: float
    simulation_pressure_bar: float


@dataclass(frozen=True)
class GOMCIOPaths:
    python_file_directory: Path
    path_gomc_runs: Path
    path_gomc_template: Path
    namd_box_0_dir: Path
    namd_box_1_dir: Optional[Path]
    previous_gomc_dir: Optional[Path]


# ----------------------------- Helpers -----------------------------

def _load_text(p: Path) -> str:
    return p.read_text()


def _save_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s)


def _rel(p: Path, base: Path) -> str:
    """Return POSIX relative path from base to p (works across siblings)."""
    return os.path.relpath(str(p), start=str(base)).replace("\\", "/")


def _build_parameters_block(params_files: Iterable[Path], relative_to: Path) -> str:
    lines = []
    for p in params_files:
        p = Path(p)
        if p.is_absolute():
            rel = _rel(p, relative_to)
        else:
            # keep author-provided relative path as-is
            rel = p.as_posix()
        lines.append(f"Parameters \t {rel}\n")
    return "".join(lines)


def _strip_box1_binary_restart_lines(template_text: str) -> str:
    out = []
    for line in template_text.splitlines(keepends=True):
        toks = line.split()
        if len(toks) >= 2 and toks[0] in {"binCoordinates", "extendedSystem", "binVelocities"} and toks[1] == "1":
            continue
        out.append(line)
    return "".join(out)


def _read_last_xsc_dims(xsc_path: Path) -> Tuple[float, float, float]:
    """
    Read last line of XSC. Support both layouts:
      primary: [1]=Lx, [5]=Ly, [9]=Lz
      fallback: [1]=Lx, [4]=Ly, [7]=Lz
    """
    lines = xsc_path.read_text().splitlines()
    if not lines:
        raise ValueError(f"Empty XSC: {xsc_path}")
    toks = lines[-1].split()

    def _try(idx):
        try:
            return float(toks[idx])
        except (IndexError, ValueError):
            return None

    lx = _try(1); ly = _try(5); lz = _try(9)
    if lx is not None and ly is not None and lz is not None and (ly != 0.0 or lz != 0.0):
        return lx, ly, lz

    ly_fb = _try(4); lz_fb = _try(7)
    if lx is not None and ly_fb is not None and lz_fb is not None:
        return lx, ly_fb, lz_fb

    raise ValueError(f"Malformed XSC line in {xsc_path}: {lines[-1]!r}")


def _read_pdb_cryst1_dims(pdb_path: Path) -> Tuple[float, float, float]:
    for line in pdb_path.read_text().splitlines():
        if line.startswith("CRYST1"):
            toks = line.split()
            try:
                a = float(toks[1]); b = float(toks[2]); c = float(toks[3])
            except (IndexError, ValueError) as e:
                raise ValueError(f"Malformed CRYST1 in {pdb_path}: {line!r}") from e
            return a, b, c
    raise ValueError(f"No CRYST1 record in {pdb_path}")


def _override_dim(read_val: float, override: Optional[float]) -> float:
    return float(override) if override is not None else float(read_val)


def _compute_adjustment_blocks(run_steps: int) -> Tuple[int, int]:
    set_max_steps_equib_adj = 10 * (10 ** 6)
    if run_steps >= set_max_steps_equib_adj:
        adj_steps = 1000 if (run_steps / 10) >= 1000 else int(run_steps / 10)
        equil_steps = 0
        return equil_steps, adj_steps
    elif int(run_steps / 10) > 0:
        equil_steps = int(run_steps / 10)
        adj_steps = int(run_steps / 10)
        if (run_steps / 10) >= 1000:
            adj_steps = 1000
        return equil_steps, adj_steps
    else:
        return 1, 1


# ----------------------------- Public API -----------------------------

def write_gomc_conf_file(
    cfg: SimulationConfig,
    io: GOMCIOPaths,
    run_no: int,
    sim: GOMCSimParams,
    starts: GOMCStartFiles,
) -> Path:
    python_dir = Path(io.python_file_directory)
    run_id = format_cycle_id(run_no, width=10)
    gomc_newdir = python_dir / io.path_gomc_runs / run_id
    gomc_newdir.mkdir(parents=True, exist_ok=True)

    tpl_path = python_dir / io.path_gomc_template
    template = _load_text(tpl_path)

    params_files = getattr(cfg, "starting_ff_file_list_gomc", []) or []
    params_block = _build_parameters_block(params_files, relative_to=gomc_newdir)
    out = template.replace("all_parameter_files", params_block)

    # Box 0: always from NAMD previous step
    prev_namd0_rel = _rel(io.namd_box_0_dir, gomc_newdir)
    out = out.replace("coor_box_0_file", f"{prev_namd0_rel}/namdOut.restart.coor")
    out = out.replace("xsc_box_0_file",  f"{prev_namd0_rel}/namdOut.restart.xsc")
    out = out.replace("vel_box_0_file",  f"{prev_namd0_rel}/namdOut.restart.vel")

    # PDB/PSF for box 0: fresh vs restart
    if io.previous_gomc_dir is None:
        pdb0_rel = _rel(python_dir / starts.starting_pdb_box_0_file, gomc_newdir)
        psf0_rel = _rel(python_dir / starts.starting_psf_box_0_file, gomc_newdir)
        out = out.replace("pdb_file_box_0_file", pdb0_rel)
        out = out.replace("psf_file_box_0_file", psf0_rel)
        out = out.replace("Restart_Checkpoint_file", f"false {'Output_data_restart.chk'}")
    else:
        prev_gomc_rel = _rel(io.previous_gomc_dir, gomc_newdir)
        out = out.replace("pdb_file_box_0_file", f"{prev_gomc_rel}/Output_data_BOX_0_restart.pdb")
        out = out.replace("psf_file_box_0_file", f"{prev_gomc_rel}/Output_data_BOX_0_restart.psf")

    # Box 0 dims from xsc
    xsc0 = io.namd_box_0_dir / "namdOut.restart.xsc"
    lx0, ly0, lz0 = _read_last_xsc_dims(xsc0)
    out = out.replace("x_dim_box_0", str(lx0))
    out = out.replace("y_dim_box_0", str(ly0))
    out = out.replace("z_dim_box_0", str(lz0))

    # Box 1 branches
    if cfg.simulation_type in {"GEMC", "GCMC"}:
        if (cfg.simulation_type == "GCMC") or (cfg.simulation_type == "GEMC" and cfg.only_use_box_0_for_namd_for_gemc):
            if io.previous_gomc_dir is None:
                out = _strip_box1_binary_restart_lines(out)
                pdb1_rel = _rel(python_dir / starts.starting_pdb_box_1_file, gomc_newdir)
                psf1_rel = _rel(python_dir / starts.starting_psf_box_1_file, gomc_newdir)
                out = out.replace("pdb_file_box_1_file", pdb1_rel)
                out = out.replace("psf_file_box_1_file", psf1_rel)

                a1, b1, c1 = _read_pdb_cryst1_dims(python_dir / starts.starting_pdb_box_1_file)
                set_dims = getattr(cfg, "set_dims_box_1_list", [None, None, None]) or [None, None, None]
                x1 = _override_dim(a1, set_dims[0])
                y1 = _override_dim(b1, set_dims[1])
                z1 = _override_dim(c1, set_dims[2])
                out = out.replace("x_dim_box_1", str(x1))
                out = out.replace("y_dim_box_1", str(y1))
                out = out.replace("z_dim_box_1", str(z1))
            else:
                prev_gomc_rel = _rel(io.previous_gomc_dir, gomc_newdir)
                out = out.replace("coor_box_1_file", f"{prev_gomc_rel}/Output_data_BOX_1_restart.coor")
                out = out.replace("xsc_box_1_file",  f"{prev_gomc_rel}/Output_data_BOX_1_restart.xsc")
                out = out.replace("vel_box_1_file",  f"{prev_gomc_rel}/Output_data_BOX_1_restart.vel")

                xsc1_prev = io.previous_gomc_dir / "Output_data_BOX_1_restart.xsc"
                lx1, ly1, lz1 = _read_last_xsc_dims(xsc1_prev)
                out = out.replace("x_dim_box_1", str(lx1))
                out = out.replace("y_dim_box_1", str(ly1))
                out = out.replace("z_dim_box_1", str(lz1))
        else:
            assert io.namd_box_1_dir is not None, "namd_box_1_dir is required for GEMC with both boxes."
            prev_namd1_rel = _rel(io.namd_box_1_dir, gomc_newdir)
            out = out.replace("coor_box_1_file", f"{prev_namd1_rel}/namdOut.restart.coor")
            out = out.replace("xsc_box_1_file",  f"{prev_namd1_rel}/namdOut.restart.xsc")
            out = out.replace("vel_box_1_file",  f"{prev_namd1_rel}/namdOut.restart.vel")
            xsc1 = io.namd_box_1_dir / "namdOut.restart.xsc"
            lx1, ly1, lz1 = _read_last_xsc_dims(xsc1)
            out = out.replace("x_dim_box_1", str(lx1))
            out = out.replace("y_dim_box_1", str(ly1))
            out = out.replace("z_dim_box_1", str(lz1))

    # restart_true_or_false
    if cfg.simulation_type in {"GEMC", "GCMC"}:
        if (cfg.simulation_type == "GCMC" and io.previous_gomc_dir is None) or \
           (cfg.simulation_type == "GEMC" and cfg.only_use_box_0_for_namd_for_gemc and io.previous_gomc_dir is None):
            out = out.replace("restart_true_or_false", "false")
        else:
            out = out.replace("restart_true_or_false", "true")
    else:
        out = out.replace("restart_true_or_false", "true")

    # Steps and thermo
    out = out.replace("GOMC_Run_Steps", str(int(sim.gomc_run_steps)))
    out = out.replace("GOMC_RST_Coor_CKpoint_Steps", str(int(sim.gomc_rst_coor_ckpoint_steps)))
    out = out.replace("GOMC_console_BLKavg_Hist_Steps", str(int(sim.gomc_console_blkavg_hist_steps)))
    out = out.replace("GOMC_Hist_sample_Steps", str(int(sim.gomc_hist_sample_steps)))
    out = out.replace("System_temp_set", str(sim.simulation_temp_k))
    out = out.replace("System_press_set", str(sim.simulation_pressure_bar))

    equil_steps, adj_steps = _compute_adjustment_blocks(sim.gomc_run_steps)
    if "GOMC_Equilb_Steps" in out:
        out = out.replace("GOMC_Equilb_Steps", str(int(equil_steps)))
    if "GOMC_Adj_Steps" in out:
        out = out.replace("GOMC_Adj_Steps", str(int(adj_steps)))

    # GCMC ChemPot/Fugacity
    if cfg.simulation_type == "GCMC":
        mode = getattr(cfg, "GCMC_ChemPot_or_Fugacity", None)
        mapping = getattr(cfg, "GCMC_ChemPot_or_Fugacity_dict", None)
        keys = getattr(cfg, "GCMC_ChemPot_or_Fugacity_dict_keys", None)
        if not mode:
            out = out.replace("mu_ChemPot_K_or_P_Fugacitiy_bar_all", "")
        elif mode in {"ChemPot", "Fugacity"}:
            items = keys if keys else (mapping.keys() if mapping else [])
            lines = []
            for k in items:
                v = mapping[k]
                lines.append(f"{mode} \t {k} \t {v}\n")
            out = out.replace("mu_ChemPot_K_or_P_Fugacitiy_bar_all", "".join(lines))
            log.info(f"GCMC using {mode}: {mapping}")
        else:
            log.warning("Warning: There is in error in the chemical potential settings for GCMC simulation.")

    if io.previous_gomc_dir is not None:
        # Tests expect checkpoint path relative to project root (python_file_directory),
        # e.g., 'GOMC/0000000003/Output_data_restart.chk'
        prev_gomc_rel_chk = _rel(io.previous_gomc_dir, io.python_file_directory)
        out = out.replace(
            "Restart_Checkpoint_file",
            f"true {prev_gomc_rel_chk}/Output_data_restart.chk",
        )
    else:
        if "Restart_Checkpoint_file" in out:
            out = out.replace("Restart_Checkpoint_file", f"false {'Output_data_restart.chk'}")

    out_path = gomc_newdir / "in.conf"
    _save_text(out_path, out)
    log.info(f"[GOMC] Wrote config: {out_path}")
    return gomc_newdir
