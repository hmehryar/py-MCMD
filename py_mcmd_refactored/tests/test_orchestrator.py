# tests/test_orchestrator.py
import logging
import pytest
from orchestrator.manager import SimulationOrchestrator

class DummyConfig:
    """Minimal config stub for testing SimulationOrchestrator."""
    def __init__(self):
        self.starting_at_cycle_namd_gomc_sims = 0
        self.total_cycles_namd_gomc_sims = 2


def test_orchestrator_run_logs_start_and_completion(caplog):
    # Arrange: create dummy config and orchestrator
    cfg = DummyConfig()
    orch = SimulationOrchestrator(cfg)

    # Capture INFO logs
    caplog.set_level(logging.INFO)

    # Act: run the orchestrator
    orch.run()

    # Assert: key log messages are emitted
    assert "Starting coupled NAMD↔GOMC simulation" in caplog.text
    assert "All cycles completed." in caplog.text

    #test it by running 
    #python -m pytest -q
