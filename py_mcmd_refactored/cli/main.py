# py_mcmd/cli/main.py

import argparse
import json
import os
import sys
import logging
from pprint import pprint  # pretty-print the object


sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")



# from  config.models import load_simulation_config
# from orchestrator.manager import SimulationOrchestrator
from config.models import load_simulation_config
from orchestrator.manager import SimulationOrchestrator

# *************************************************
# The python arguments that need to be selected to run the simulations (start)
# *************************************************
def parse_args(argv=None):
    arg_parser = argparse.ArgumentParser(
        prog="py-mcmd",
        description="Run coupled NAMD ↔ GOMC simulations based on a JSON spec",
    )
    # get the filename with the user required input
    arg_parser.add_argument(
        "-f", "--file",
        type=str,
        default="user_input_NAMD_GOMC.json",
        help="Defines the variable inputs file used for the hybrid NAMD/GOMC simulation script. "
        "This file (i.e., the user_input_variables_NAMD_GOMC.json file) is required "
        "to run the hybrid simulation.",
    )
    arg_parser.add_argument(
        "-namd_sims_order",
        "--namd_simulation_order",
        help="This sets the NAMD simulation to be run in series or parallel. "
        "The data is entered only as series or parallel (default = series). "
        "This is only relevant for the GEMC ensemble when utilizing two (2) NAMD simulation "
        "boxes "
        "(i.e., only_use_box_0_for_namd_for_gemc = False  --> both box 0 and box 1)."
        "The GCMC, NVT, NPT, or the GEMC ensembles when using only one (1) "
        "NAMD simulation box "
        "(i.e., only_use_box_0_for_namd_for_gemc = True --> only box 0) "
        "are always run in series, since there is nothing to run in parallel."
        "Note: this feature was added so the user can minimize the load on the GPU "
        "by running both NAMD simulations in parallel.",
        type=str,
    )
    arg_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    # return arg_parser.parse_args()
    args = arg_parser.parse_args(argv)

    # --- validate file existence ---
    if args.file:
        if os.path.exists(args.file):
            logging.info("Reading data from <%s> file.", args.file)
        else:
            logging.error("Console file <%s> does not exist!", args.file)
            sys.exit(1)

    # --- validate NAMD simulation order ---
    if args.namd_simulation_order in ("series", "parallel"):
        logging.info(
            "The NAMD simulations shall be run in <%s>.",
            args.namd_simulation_order
        )
    else:
        # default to series if unspecified or invalid
        args.namd_simulation_order = "series"
        logging.warning(
            "The NAMD simulations are not set to 'parallel' or 'series'. "
            "Therefore, defaulting to <%s>.",
            args.namd_simulation_order
        )

    logging.debug(
        "parse_args: file=%s, namd_simulation_order=%s",
        args.file, args.namd_simulation_order
    )
    return args
# *************************************************
# The python arguments that need to be selected to run the simulations (end)
# *************************************************

def main():
    args = parse_args()
    # logging setup
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    force=True  # <--- this resets any prior config
    )
    # load + validate config
    try:
        cfg = load_simulation_config(args.file)
        logging.info("Loaded simulation config from %s", args.file)
    except Exception as e:
        logging.error("Failed to load config: %s", e)
        sys.exit(1)

    # hand off to the orchestrator
    sim = SimulationOrchestrator(cfg)
    logging.info("Configuration loaded and orchestrator constructed successfully.")

    # sim.run()  # or sim.execute_cycles()

if __name__ == "__main__":
    main()

# python cli/main.py -f ../user_input_NAMD_GOMC.json --verbose