# config/models.py
import json
import re
from pathlib import Path
from typing import List, Dict
from pydantic import BaseModel, Field


class SimulationConfig(BaseModel): 
    total_cycles_namd_gomc_sims: int = Field(..., alias="total_cycles_namd_gomc_sims")
    starting_at_cycle_namd_gomc_sims: int
    gomc_use_CPU_or_GPU: str
    simulation_type: str
    only_use_box_0_for_namd_for_gemc: bool
    no_core_box_0: int
    no_core_box_1: int
    simulation_temp_k: float
    simulation_pressure_bar: float
    GCMC_ChemPot_or_Fugacity: str
    GCMC_ChemPot_or_Fugacity_dict: Dict[str, float]
    namd_minimize_mult_scalar: int
    namd_run_steps: int
    gomc_run_steps: int
    set_dims_box_0_list: List[float]
    set_dims_box_1_list: List[float]
    set_angle_box_0_list: List[int]
    set_angle_box_1_list: List[int]
    starting_ff_file_list_gomc: List[str]
    starting_ff_file_list_namd: List[str]
    starting_pdb_box_0_file: str
    starting_psf_box_0_file: str
    starting_pdb_box_1_file: str
    starting_psf_box_1_file: str
    namd2_bin_directory: str
    gomc_bin_directory: str

    class ConfigDict:
        validate_by_name = True
        extra = "forbid"


def load_simulation_config(path: str) -> SimulationConfig:
    """
    Load a JSON config file, stripping out // comments, and parse into SimulationConfig.
    """
    text = Path(path).read_text()
    # strip out any //-style comments
    cleaned = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    data = json.loads(cleaned)
    return SimulationConfig(**data)

# wherever you need to load and validate your parameters:

# from config.models import load_simulation_config

# cfg = load_simulation_config("user_input_NAMD_GOMC.json")
