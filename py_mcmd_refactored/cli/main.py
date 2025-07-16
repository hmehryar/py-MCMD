# py_mcmd/cli/main.py

import argparse
import sys
import logging

sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

from config.models import load_simulation_config
from orchestrator.manager import SimulationOrchestrator


def parse_args():
    p = argparse.ArgumentParser(
        prog="py-mcmd",
        description="Run coupled NAMD ↔ GOMC simulations based on a JSON spec",
    )
    p.add_argument(
        "-c", "--config",
        type=str,
        default="user_input_NAMD_GOMC.json",
        help="Path to simulation JSON config"
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    return p.parse_args()


def main():
    args = parse_args()

    # logging setup
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    # load + validate config
    try:
        cfg = load_simulation_config(args.config)
    except Exception as e:
        logging.error("Failed to load config: %s", e)
        sys.exit(1)

    # hand off to the orchestrator
    sim = SimulationOrchestrator(cfg)
    sim.run()  # or sim.execute_cycles()

if __name__ == "__main__":
    main()

# python cli/main.py -c ../user_input_NAMD_GOMC.json --verbose