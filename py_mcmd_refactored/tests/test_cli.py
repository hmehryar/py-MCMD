# tests/test_cli.py

import sys
sys.path.insert(0, "/home/arsalan/wsu-gomc/py-MCMD-hm/py_mcmd_refactored")

import pytest

import os
import logging

from cli.main import parse_args


def test_parse_args_valid_file_and_order(tmp_path, caplog):
    # Arrange: create a dummy JSON config file
    config_file = tmp_path / "user.json"
    config_file.write_text("{}")

    # Act: parse args with existing file and valid order
    caplog.set_level(logging.INFO)
    args = parse_args(["--file", str(config_file), "--namd_simulation_order", "parallel"])

    # Assert: args values and INFO logs
    assert args.file == str(config_file)
    assert args.namd_simulation_order == "parallel"
    assert f"Reading data from <{config_file}> file." in caplog.text
    assert "shall be run in <parallel>." in caplog.text


def test_parse_args_default_order_on_invalid(tmp_path, caplog):
    # Arrange: create a dummy JSON config file
    config_file = tmp_path / "user.json"
    config_file.write_text("{}")

    # Act: parse args with invalid order
    caplog.set_level(logging.WARNING)
    args = parse_args(["--file", str(config_file), "--namd_simulation_order", "invalid_order"])

    # Assert: default to 'series' and emit WARNING
    assert args.namd_simulation_order == "series"
    assert "defaulting to <series>" in caplog.text or "defaulting to <series>." in caplog.text


def test_parse_args_exit_on_missing_file(tmp_path):
    # Arrange: define a non-existent file
    nonexist = tmp_path / "nope.json"

    # Act & Assert: SystemExit with code 1
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--file", str(nonexist)])
    assert exc_info.value.code == 1