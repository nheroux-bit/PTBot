"""Tests for ptbot.db_sync — S3-backed SQLite database sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ptbot.db_sync import pull_db, push_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(returncode: int = 0, stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stderr = stderr
    return proc


S3_URI = "s3://my-bucket/ptbot/ptbot.db"


# ---------------------------------------------------------------------------
# pull_db
# ---------------------------------------------------------------------------


def test_pull_db_success_returns_true(tmp_path: Path) -> None:
    """pull_db should return True when aws s3 cp exits 0."""
    db_file = tmp_path / "ptbot.db"
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(0)) as mock_run:
        result = pull_db(S3_URI, db_file)

    assert result is True
    cmd = mock_run.call_args[0][0]
    assert cmd == ["aws", "s3", "cp", S3_URI, str(db_file)]


def test_pull_db_creates_parent_directories(tmp_path: Path) -> None:
    """pull_db should create missing parent directories before running aws."""
    db_file = tmp_path / "nested" / "dir" / "ptbot.db"
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(0)):
        pull_db(S3_URI, db_file)
    assert db_file.parent.exists()


def test_pull_db_object_not_found_returns_false(tmp_path: Path) -> None:
    """A non-zero exit from aws s3 cp (object not found) should return False."""
    db_file = tmp_path / "ptbot.db"
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(1, "NoSuchKey")):
        result = pull_db(S3_URI, db_file)
    assert result is False


def test_pull_db_aws_error_returns_false(tmp_path: Path) -> None:
    """Any non-zero aws exit code should return False without raising."""
    db_file = tmp_path / "ptbot.db"
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(255, "error")):
        result = pull_db(S3_URI, db_file)
    assert result is False


# ---------------------------------------------------------------------------
# push_db
# ---------------------------------------------------------------------------


def test_push_db_success_returns_true(tmp_path: Path) -> None:
    """push_db should return True when aws s3 cp exits 0."""
    db_file = tmp_path / "ptbot.db"
    db_file.write_bytes(b"data")
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(0)) as mock_run:
        result = push_db(db_file, S3_URI)

    assert result is True
    cmd = mock_run.call_args[0][0]
    assert cmd == ["aws", "s3", "cp", str(db_file), S3_URI]


def test_push_db_missing_local_file_returns_false_without_running_aws(
    tmp_path: Path,
) -> None:
    """push_db should skip aws and return False when the local file does not exist."""
    db_file = tmp_path / "nonexistent.db"
    with patch("ptbot.db_sync.subprocess.run") as mock_run:
        result = push_db(db_file, S3_URI)

    assert result is False
    mock_run.assert_not_called()


def test_push_db_aws_failure_returns_false(tmp_path: Path) -> None:
    """A non-zero exit from aws s3 cp should return False."""
    db_file = tmp_path / "ptbot.db"
    db_file.write_bytes(b"data")
    with patch("ptbot.db_sync.subprocess.run", return_value=_make_proc(1, "AccessDenied")):
        result = push_db(db_file, S3_URI)
    assert result is False
