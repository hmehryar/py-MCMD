# config/models.py
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Literal

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class SimulationConfig(BaseModel):
    """
    Pydantic model for hybrid NAMD↔GOMC simulation configuration.
    Enforces type checks, ranges, and cross-field constraints.
    """
    total_cycles_namd_gomc_sims: int = Field(
        ..., alias="total_cycles_namd_gomc_sims", ge=0,
        description="Total number of coupled cycles (>=0)"
    )
    starting_at_cycle_namd_gomc_sims: int = Field(
        ..., ge=0,
        description="Starting cycle index (>=0)"
    )
    gomc_use_CPU_or_GPU: Literal["CPU", "GPU"]
    simulation_type: Literal["GEMC", "GCMC", "NPT", "NVT"]
    only_use_box_0_for_namd_for_gemc: bool
    no_core_box_0: int = Field(..., ge=0)
    no_core_box_1: int = Field(..., ge=0)
    simulation_temp_k: float = Field(..., gt=0)
    simulation_pressure_bar: Optional[float] = Field(..., ge=0)
    GCMC_ChemPot_or_Fugacity: Optional[Literal["ChemPot", "Fugacity"]]
    GCMC_ChemPot_or_Fugacity_dict: Optional[Dict[str, float]]
    namd_minimize_mult_scalar: int = Field(..., ge=0)
    namd_run_steps: int = Field(..., ge=0)
    gomc_run_steps: int = Field(..., ge=0)
    set_dims_box_0_list: List[Optional[float]]
    set_dims_box_1_list: List[Optional[float]]
    set_angle_box_0_list: List[Optional[int]]
    set_angle_box_1_list: List[Optional[int]]
    starting_ff_file_list_gomc: List[str]
    starting_ff_file_list_namd: List[str]
    starting_pdb_box_0_file: str
    starting_psf_box_0_file: str
    starting_pdb_box_1_file: Optional[str]
    starting_psf_box_1_file: Optional[str]
    namd2_bin_directory: str
    gomc_bin_directory: str


     # ---- tolerances (with defaults) ----
    allowable_error_fraction_vdw_plus_elec: float = Field(5e-3, ge=0)
    allowable_error_fraction_potential: float = Field(5e-3, ge=0)
    max_absolute_allowable_kcal_fraction_vdw_plus_elec: float = Field(0.5, ge=0)

    # ---- engine step params (initialized later) ----
    gomc_console_blkavg_hist_steps: int = 0
    gomc_rst_coor_ckpoint_steps: int = 0
    gomc_hist_sample_steps: int = 0
    namd_rst_dcd_xst_steps: int = 0
    namd_console_blkavg_e_and_p_steps: int = 0

    # Pydantic v2 configuration
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid"
    )

    @field_validator('set_dims_box_0_list', 'set_dims_box_1_list', mode='before')
    def validate_dims_list(cls, v):
        if v is None:
            return [None, None, None]
        if not isinstance(v, list) or len(v) != 3:
            raise ValueError("set_dims_box_X_list must be a list of three floats or None")
        for x in v:
            if x is not None and x <= 0:
                raise ValueError("All dimensions must be > 0 or None")
        return v

    @field_validator('set_angle_box_0_list', 'set_angle_box_1_list', mode='before')
    def validate_angle_list(cls, v):
        if v is None:
            return [None, None, None]
        if not isinstance(v, list) or len(v) != 3:
            raise ValueError("set_angle_box_X_list must be a list of three ints or None")
        for x in v:
            if x is not None and x != 90:
                raise ValueError("All angles must be 90 or None")
        return v

    @model_validator(mode='after')
    def cross_field_validations(self):
        # Alias model fields to local variables
        sim = self.simulation_type
        use0 = self.only_use_box_0_for_namd_for_gemc
        nc1 = self.no_core_box_1
        pres = self.simulation_pressure_bar
        chempot = self.GCMC_ChemPot_or_Fugacity
        chempot_dict = self.GCMC_ChemPot_or_Fugacity_dict

        # GEMC: require >0 cores on box 1 if two-box run
        if sim == 'GEMC' and not use0:
            if nc1 <= 0:
                raise ValueError(
                    "no_core_box_1 must be > 0 when running two NAMD boxes in GEMC"
                )

        # NPT: pressure must be non-negative
        if sim == 'NPT' and (pres is None or pres < 0):
            raise ValueError(
                "simulation_pressure_bar must be >= 0 for NPT simulations"
            )

        # GCMC: require chempot and dict, with valid numeric values
        if sim == 'GCMC':
            if chempot is None or chempot_dict is None:
                raise ValueError(
                    "GCMC_ChemPot_or_Fugacity and its dict must be provided for GCMC simulations"
                )
            for key, val in chempot_dict.items():
                if not isinstance(val, (int, float)):
                    raise TypeError(
                        "GCMC_ChemPot_or_Fugacity_dict values must be numeric"
                    )
                if chempot == 'Fugacity' and val < 0:
                    raise ValueError(
                        "Fugacity values must be >= 0"
                    )
        else:
            # clear GCMC fields when not using GCMC
            object.__setattr__(self, 'GCMC_ChemPot_or_Fugacity', None)
            object.__setattr__(
                self, 'GCMC_ChemPot_or_Fugacity_dict', None
            )

        return self
    def __init__(self, **data):
        super().__init__(**data)

        # Derive the per-engine step parameters from run steps
        gsteps = int(self.gomc_run_steps)
        nsteps = int(self.namd_run_steps)

        object.__setattr__(self, "gomc_console_blkavg_hist_steps", gsteps)
        object.__setattr__(self, "gomc_rst_coor_ckpoint_steps", gsteps)
        object.__setattr__(self, "gomc_hist_sample_steps", min(500, int(gsteps / 10)))
        object.__setattr__(self, "namd_rst_dcd_xst_steps", nsteps)
        object.__setattr__(self, "namd_console_blkavg_e_and_p_steps", nsteps)


def load_simulation_config(path: str) -> SimulationConfig:
    """
    Load a JSON config file, stripping out // comments, and parse into SimulationConfig.
    """
    text = Path(path).read_text()
    cleaned = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    data = json.loads(cleaned)
    return SimulationConfig(**data)


def main():
    cfg = load_simulation_config("../user_input_NAMD_GOMC.json")
    # Pydantic V2: use model_dump_json for formatted output
    print(cfg.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
