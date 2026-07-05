from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.onthefly_processor import (
    AMU_PER_ANGSTROM3_TO_G_PER_CM3,
    K_TO_KCAL_MOL,
    OnTheFlyProcessor,
    _parse_gomc_log,
    _parse_namd_log,
)


def _cfg(
    tmp_path: Path,
    simulation_type: str = "NVT",
) -> SimpleNamespace:
    return SimpleNamespace(
        path_namd_runs=str(tmp_path / "NAMD"),
        path_gomc_runs=str(tmp_path / "GOMC"),
        simulation_type=simulation_type,
    )


def _write_log(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        text,
        encoding="utf-8",
    )


def _namd_log(
    *,
    steps: tuple[int, ...] = (0, 5),
    mass: float = 100.0,
) -> str:
    lines = [
        f"Info: TOTAL MASS = {mass}\n",
        (
            "ETITLE: TS POTENTIAL ELECT "
            "PRESSURE VOLUME\n"
        ),
    ]

    for step in steps:
        lines.append(
            (
                f"ENERGY: {step} "
                "-10.0 -2.0 1.0 1000.0\n"
            )
        )

    return "".join(lines)


def _gomc_log(
    *,
    box_no: int = 0,
    steps: tuple[int, ...] = (0,),
) -> str:
    lines = [
        "ETITLE: STEP TOTAL TOTAL_ELECT\n",
        (
            "STITLE: STEP PRESSURE "
            "VOLUME TOT_DENSITY\n"
        ),
    ]

    for step in steps:
        lines.extend(
            [
                (
                    f"ENER_{box_no}: "
                    f"{step} 1000.0 500.0\n"
                ),
                (
                    f"STAT_{box_no}: "
                    f"{step} 1.5 2000.0 900.0\n"
                ),
            ]
        )

    return "".join(lines)

def test_parse_namd_log_normalizes_steps_and_calculates_density():
    (
        titles,
        density_titles,
        rows,
        last_ts,
    ) = _parse_namd_log(
        _namd_log().splitlines(
            keepends=True
        ),
        current_step=100,
    )

    assert titles == [
        "ETITLE:",
        "TS",
        "POTENTIAL",
        "ELECT",
        "PRESSURE",
        "VOLUME",
    ]
    assert density_titles == [
        "TS",
        "POTENTIAL",
        "ELECT",
        "PRESSURE",
        "VOLUME",
        "DENSITY",
    ]

    assert [
        row[1]
        for row, _ in rows
    ] == [
        "100",
        "105",
    ]

    assert last_ts == 105

    expected_density = (
        AMU_PER_ANGSTROM3_TO_G_PER_CM3
        * 100.0
        / 1000.0
        * 1000.0
    )

    assert rows[0][1] == pytest.approx(
        expected_density
    )
    assert rows[1][1] == pytest.approx(
        expected_density
    )

@pytest.mark.parametrize(
    "box_no",
    [0, 1],
)
def test_parse_gomc_log_merges_rows_offsets_steps_and_converts_units(
    box_no: int,
):
    (
        titles,
        merged_titles,
        kcal_titles,
        merged_rows,
        kcal_rows,
        raw_lines,
        last_step,
    ) = _parse_gomc_log(
        _gomc_log(
            box_no=box_no,
            steps=(0, 5),
        ).splitlines(
            keepends=True
        ),
        box_no=box_no,
        current_step=10,
    )

    assert titles == [
        "ETITLE:",
        "STEP",
        "TOTAL",
        "TOTAL_ELECT",
    ]

    assert merged_titles == [
        "#STEP",
        "TOTAL",
        "TOTAL_ELECT",
        "PRESSURE",
        "VOLUME",
        "TOT_DENSITY",
    ]

    assert kcal_titles == merged_titles

    assert [
        row[0]
        for row in merged_rows
    ] == [
        "10",
        "15",
    ]

    assert [
        row[0]
        for row in kcal_rows
    ] == [
        "10",
        "15",
    ]

    assert last_step == 15

    assert float(
        kcal_rows[0][1]
    ) == pytest.approx(
        1000.0 * K_TO_KCAL_MOL
    )

    assert float(
        kcal_rows[0][2]
    ) == pytest.approx(
        500.0 * K_TO_KCAL_MOL
    )

    assert float(
        kcal_rows[0][-1]
    ) == pytest.approx(
        0.9
    )

    raw_energy_lines = [
        content
        for kind, content in raw_lines
        if kind == "ENER"
    ]

    raw_stat_lines = [
        content
        for kind, content in raw_lines
        if kind == "STAT"
    ]

    assert "10" in raw_energy_lines[0]
    assert "15" in raw_energy_lines[1]
    assert "10" in raw_stat_lines[0]
    assert "15" in raw_stat_lines[1]

def test_resolve_log_path_prefers_runtime_then_falls_back_to_disk(
    tmp_path: Path,
):
    runtime_dir = (
        tmp_path
        / "managed"
        / "NAMD"
        / "0000000000_a"
    )

    disk_dir = (
        tmp_path
        / "NAMD"
        / "0000000000_a"
    )

    runtime_log = runtime_dir / "out.dat"
    disk_log = disk_dir / "out.dat"

    _write_log(
        disk_log,
        "disk\n",
    )
    _write_log(
        runtime_log,
        "runtime\n",
    )

    assert (
        OnTheFlyProcessor._resolve_log_path(
            runtime_dir,
            disk_dir,
        )
        == runtime_log
    )

    runtime_log.unlink()

    assert (
        OnTheFlyProcessor._resolve_log_path(
            runtime_dir,
            disk_dir,
        )
        == disk_log
    )

    disk_log.unlink()

    assert (
        OnTheFlyProcessor._resolve_log_path(
            runtime_dir,
            disk_dir,
        )
        is None
    )

def test_process_cycle_appends_rows_once_per_cycle_and_preserves_step_offsets(
    tmp_path: Path,
):
    managed_root = tmp_path / "managed"
    combined_dir = tmp_path / "combined"
    cfg = _cfg(tmp_path)

    _write_log(
        (
            managed_root
            / "NAMD"
            / "0000000000_a"
            / "out.dat"
        ),
        _namd_log(
            steps=(0, 5),
        ),
    )

    _write_log(
        (
            managed_root
            / "GOMC"
            / "0000000001"
            / "out.dat"
        ),
        _gomc_log(
            steps=(0,),
        ),
    )

    _write_log(
        (
            managed_root
            / "NAMD"
            / "0000000002_a"
            / "out.dat"
        ),
        _namd_log(
            steps=(0, 5),
        ),
    )

    _write_log(
        (
            managed_root
            / "GOMC"
            / "0000000003"
            / "out.dat"
        ),
        _gomc_log(
            steps=(0,),
        ),
    )

    processor = OnTheFlyProcessor(
        cfg,
        combined_dir,
        managed_root=managed_root,
    )

    try:
        processor.process_cycle(
            0,
            1,
        )
        processor.process_cycle(
            2,
            3,
        )

    finally:
        processor.close()

    namd_lines = (
        combined_dir
        / "NAMD_data_box_0.txt"
    ).read_text().splitlines()

    assert sum(
        line.startswith("ETITLE:")
        for line in namd_lines
    ) == 1

    energy_lines = [
        line
        for line in namd_lines
        if line.startswith("ENERGY:")
    ]

    assert [
        line.split()[1]
        for line in energy_lines
    ] == [
        "0",
        "5",
        "5",
        "10",
    ]

    density_lines = (
        combined_dir
        / "NAMD_data_density_box_0.txt"
    ).read_text().splitlines()

    assert density_lines[0].endswith(
        "DENSITY"
    )

    assert len(density_lines) == 5

    gomc_stat_lines = (
        combined_dir
        / "GOMC_Energies_Stat_box_0.txt"
    ).read_text().splitlines()

    assert sum(
        line.startswith("#STEP")
        for line in gomc_stat_lines
    ) == 1

    assert [
        line.split()[0]
        for line in gomc_stat_lines[1:]
    ] == [
        "5",
        "10",
    ]

    combined_lines = (
        combined_dir
        / "combined_NAMD_GOMC_data_box_0.txt"
    ).read_text().splitlines()

    assert sum(
        line.startswith("#ENGINE")
        for line in combined_lines
    ) == 1

    assert [
        line.split()[0]
        for line in combined_lines[1:]
    ] == [
        "NAMD",
        "NAMD",
        "GOMC",
        "NAMD",
        "NAMD",
        "GOMC",
    ]

    assert [
        line.split()[1]
        for line in combined_lines[1:]
    ] == [
        "0",
        "5",
        "5",
        "5",
        "10",
        "10",
    ]
def test_process_cycle_writes_kcal_and_density_converted_gomc_output(
    tmp_path: Path,
):
    managed_root = tmp_path / "managed"
    combined_dir = tmp_path / "combined"
    cfg = _cfg(tmp_path)

    _write_log(
        (
            managed_root
            / "NAMD"
            / "0000000000_a"
            / "out.dat"
        ),
        _namd_log(
            steps=(0, 5),
        ),
    )

    _write_log(
        (
            managed_root
            / "GOMC"
            / "0000000001"
            / "out.dat"
        ),
        _gomc_log(
            steps=(0,),
        ),
    )

    processor = OnTheFlyProcessor(
        cfg,
        combined_dir,
        managed_root=managed_root,
    )

    try:
        processor.process_cycle(
            0,
            1,
        )

    finally:
        processor.close()

    lines = (
        combined_dir
        / (
            "GOMC_Energies_Stat_"
            "kcal_per_mol_box_0.txt"
        )
    ).read_text().splitlines()

    assert lines[0].split() == [
        "#STEP",
        "TOTAL",
        "TOTAL_ELECT",
        "PRESSURE",
        "VOLUME",
        "TOT_DENSITY",
    ]

    values = lines[1].split()

    assert values[0] == "5"

    assert float(
        values[1]
    ) == pytest.approx(
        1000.0 * K_TO_KCAL_MOL
    )

    assert float(
        values[2]
    ) == pytest.approx(
        500.0 * K_TO_KCAL_MOL
    )

    assert float(
        values[-1]
    ) == pytest.approx(
        0.9
    )

def test_process_cycle_handles_missing_logs_without_crashing(
    tmp_path: Path,
):
    processor = OnTheFlyProcessor(
        _cfg(tmp_path),
        tmp_path / "combined",
        managed_root=tmp_path / "managed",
    )

    try:
        processor.process_cycle(
            0,
            1,
        )

    finally:
        processor.close()

    combined = (
        tmp_path
        / "combined"
        / "combined_NAMD_GOMC_data_box_0.txt"
    )

    assert combined.read_text() == ""