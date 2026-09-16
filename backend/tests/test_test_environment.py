from __future__ import annotations

import os
import subprocess
import sys


def test_database_tests_fail_clearly_when_test_database_url_is_missing() -> None:
    environment = os.environ.copy()
    environment.pop("TEST_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_database_schema.py::test_migration_is_at_latest_revision",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "TEST_DATABASE_URL is required for PostgreSQL integration tests" in output
