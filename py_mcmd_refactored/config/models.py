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

    # Core counts
    no_core_box_0: int = Field(..., ge=1) # must be a positive integer
    no_core_box_1: int = Field(..., ge=0) # may be zero if not used
    
    simulation_temp_k: float = Field(..., gt=0)
    simulation_pressure_bar: Optional[float] = None
    GCMC_ChemPot_or_Fugacity:  Optional[Literal["ChemPot", "Fugacity"]] = None
    GCMC_ChemPot_or_Fugacity_dict: Optional[Dict[str, float]] = None
    namd_minimize_mult_scalar: int = Field(..., ge=0)
    namd_run_steps: int = Field(..., ge=0)
    gomc_run_steps: int = Field(..., ge=0)
    set_dims_box_0_list: List[Optional[float]]
    set_dims_box_1_list: List[Optional[float]]
    set_angle_box_0_list: List[Optional[int]]
    set_angle_box_1_list: List[Optional[int]]
    
    # Force-field file lists (must be list[str])    
    starting_ff_file_list_gomc: List[str]
    starting_ff_file_list_namd: List[str]

    starting_pdb_box_0_file: str
    starting_psf_box_0_file: str
    starting_pdb_box_1_file: Optional[str]
    starting_psf_box_1_file: Optional[str]
    namd2_bin_directory: str
    gomc_bin_directory: str

    # run directory roots (overridable from JSON if needed)
    path_namd_runs: str = Field("NAMD")
    path_gomc_runs: str = Field("GOMC")

    # Make these truly optional so we can detect “missing”
    path_namd_template: Optional[str] = Field(default=None)
    path_gomc_template: Optional[str] = Field(default=None)

    
    # Logging
    log_dir: str = Field("logs")  # can override in JSON

    namd_minimize_steps: int = 0

    # derived (used by orchestrator/engines)
    effective_no_core_box_1: int = 0
    total_no_cores: int = 0

    @field_validator("no_core_box_0", mode="before")
    @classmethod
    def _ensure_box0_int_and_nonzero(cls, v):
        if not isinstance(v, int):
            raise TypeError(
                f"Enter no_core_box_0 as an integer; received {v!r} (type {type(v).__name__})."
            )
        if v == 0:
            raise ValueError("Enter no_core_box_0 as a non-zero number (>=1).")
        return v

    @field_validator("no_core_box_1", mode="before")
    @classmethod
    def _ensure_box1_int(cls, v):
        if not isinstance(v, int):
            raise TypeError(
                f"Enter no_core_box_1 as an integer; received {v!r} (type {type(v).__name__})."
            )
        return v

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

    @field_validator("GCMC_ChemPot_or_Fugacity_dict")
    @classmethod
    def _gcmc_dict_type(cls, v, info):
        field = info.field_name
        # Allow None when not GCMC; deeper checks happen in model-level validator
        if v is None:
            return v
        if not isinstance(v, dict):
            raise TypeError(f"ERROR: {field} must be a dictionary when using GCMC.")
        # keys must be str, values must be int/float
        for k, val in v.items():
            if not isinstance(k, str):
                raise TypeError(f"The {field} keys must be a string.")
            if not isinstance(val, (int, float)):
                raise TypeError(f"The {field} values must be an integer or float.")
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

    @model_validator(mode="after")
    def _derive_template_paths_when_missing(self):
        # Only fill in defaults if user did NOT supply a value
        if self.path_namd_template is None:
            self.path_namd_template = "required_data/config_files/NAMD.conf"

        if self.path_gomc_template is None:
            # derive from simulation_type only if not provided
            self.path_gomc_template = (
                f"required_data/config_files/GOMC_{self.simulation_type}.conf"
            )
        return self

    @field_validator("starting_ff_file_list_gomc", "starting_ff_file_list_namd", mode="after")
    @classmethod
    def _ensure_list_of_strings(cls, v: List[str], info):
        field = info.field_name
        if not isinstance(v, list):
            raise TypeError(
                f"ERROR: The {field} must be provided as a list of strings."
            )
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise TypeError(
                    f"ERROR: The {field} must be a list of strings (item {i} is {type(item).__name__})."
                )
        return v
    @model_validator(mode="after")
    def _ensemble_consistency(self):
        # --- GCMC-only checks ---
        if self.simulation_type == "GCMC":
            if self.GCMC_ChemPot_or_Fugacity_dict is None:
                raise TypeError(
                    "ERROR: enter the chemical potential or fugacity data (GCMC_ChemPot_or_Fugacity_dict) "
                    "as a dictionary when using the GCMC ensemble."
                )
            if self.GCMC_ChemPot_or_Fugacity is None:
                raise ValueError(
                    "The GCMC_ChemPot_or_Fugacity cannot be None when running the GCMC ensemble."
                )
            # If Fugacity, all values must be >= 0
            if self.GCMC_ChemPot_or_Fugacity == "Fugacity":
                for k, val in self.GCMC_ChemPot_or_Fugacity_dict.items():
                    if val < 0:
                        raise ValueError(
                            "When using Fugacity, GCMC_ChemPot_or_Fugacity_dict values must be >= 0."
                        )
        else:
            # Non-GCMC: allow these to be unset
            # (We do not auto-clear them to preserve round-tripping of configs.)
            pass

        # --- Pressure logic ---
        if self.simulation_type == "NPT":
            if not isinstance(self.simulation_pressure_bar, (int, float)):
                raise TypeError(
                    "The simulation pressure needs to be set for the NPT simulation type (int or float)."
                )
            if self.simulation_pressure_bar < 0:
                raise ValueError(
                    "The simulation pressure must be >= 0 bar for the NPT simulation type."
                )
        else:
            # Set to atmospheric (not used but required numerically by some paths)
            if self.simulation_pressure_bar is None:
                self.simulation_pressure_bar = 1.01325

        return self
    def __init__(self, **data):
        super().__init__(**data)

        # Derive the per-engine step parameters from run steps
        gsteps = int(self.gomc_run_steps)
        nsteps = int(self.namd_run_steps)

        # Tolerances
        object.__setattr__(self, "gomc_console_blkavg_hist_steps", gsteps)
        object.__setattr__(self, "gomc_rst_coor_ckpoint_steps", gsteps)
        object.__setattr__(self, "gomc_hist_sample_steps", min(500, int(gsteps / 10)))
        object.__setattr__(self, "namd_rst_dcd_xst_steps", nsteps)
        object.__setattr__(self, "namd_console_blkavg_e_and_p_steps", nsteps)
        object.__setattr__(self,"namd_minimize_steps",
            int(int(self.namd_run_steps) * int(self.namd_minimize_mult_scalar))
        )

        # Derive effective cores and totals (do *not* mutate the input fields)
        if self.simulation_type == "GEMC" and (self.only_use_box_0_for_namd_for_gemc is False):
            eff_box1 = int(self.no_core_box_1)
            total = int(self.no_core_box_0) + eff_box1
        else:
            # Not GEMC, or GEMC but only using box 0 for NAMD
            eff_box1 = 0
            total = int(self.no_core_box_0)

        object.__setattr__(self, "effective_no_core_box_1", eff_box1)
        object.__setattr__(self, "total_no_cores", total)
        
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
