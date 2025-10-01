from pathlib import Path
from typing import Optional, Tuple

def extract_pme_grid_from_out(out_path: Path) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Parse NAMD out.dat to find the line starting with:
    'Info: PME GRID DIMENSIONS <nx> <ny> <nz>'
    Returns (nx, ny, nz) or (None, None, None) if not found.
    """
    namd_x_pme_grid_dim = None
    namd_y_pme_grid_dim = None
    namd_z_pme_grid_dim = None
    try:
        with out_path.open("r") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 7 and parts[:4] == ["Info:", "PME", "GRID", "DIMENSIONS"]:
                    namd_x_pme_grid_dim = int(parts[4])
                    namd_y_pme_grid_dim = int(parts[5])
                    namd_z_pme_grid_dim = int(parts[6])
                    return namd_x_pme_grid_dim, namd_y_pme_grid_dim, namd_z_pme_grid_dim
    except FileNotFoundError:
        return None, None, None
    except Exception:
        # Be conservative: if the file is present but unparsable, return Nones
        return None, None, None
    return namd_x_pme_grid_dim, namd_y_pme_grid_dim, namd_z_pme_grid_dim