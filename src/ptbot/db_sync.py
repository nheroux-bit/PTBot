"""S3-backed SQLite database sync for cloud deployments.

Persists the local SQLite database to an S3 URI so that ephemeral cloud
environments retain deal history across runs.  Uses the AWS CLI (``aws s3
cp``) rather than boto3 to keep the Python runtime dependency-free.

The AWS CLI must be installed and configured (via environment variables or
instance profile) in the execution environment.

Typical usage in a sweep:
    from ptbot import db_sync

    db_sync.pull_db("s3://my-bucket/ptbot/ptbot.db", local_path)
    # ... run sweep ...
    db_sync.push_db(local_path, "s3://my-bucket/ptbot/ptbot.db")
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def pull_db(s3_uri: str, local_path: Path) -> bool:
    """Download the database from S3 to *local_path*.

    On a first run the S3 object may not exist yet; the function treats a
    non-zero exit code from ``aws s3 cp`` as a warning rather than an error
    so the sweep can proceed and create a fresh database locally.

    Args:
        s3_uri:     Source S3 URI, e.g. ``s3://my-bucket/ptbot/ptbot.db``.
        local_path: Destination path on the local filesystem.

    Returns:
        ``True`` if the database was downloaded, ``False`` if the object was
        not found or the download failed (warning is printed to stderr).
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[db-sync] pulling {s3_uri} → {local_path}", flush=True)
    result = subprocess.run(
        ["aws", "s3", "cp", s3_uri, str(local_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[db-sync] pull succeeded", flush=True)
        return True
    # Exit code 1 from aws s3 cp typically means the object does not exist.
    print(
        f"[db-sync] pull failed (exit {result.returncode}) — starting fresh. "
        f"stderr: {result.stderr.strip()}",
        file=sys.stderr,
    )
    return False


def push_db(local_path: Path, s3_uri: str) -> bool:
    """Upload *local_path* to S3.

    Args:
        local_path: Source path on the local filesystem.
        s3_uri:     Destination S3 URI, e.g. ``s3://my-bucket/ptbot/ptbot.db``.

    Returns:
        ``True`` on success, ``False`` on failure (stderr is printed).
    """
    if not local_path.exists():
        print(
            f"[db-sync] push skipped — local database not found: {local_path}",
            file=sys.stderr,
        )
        return False
    print(f"[db-sync] pushing {local_path} → {s3_uri}", flush=True)
    result = subprocess.run(
        ["aws", "s3", "cp", str(local_path), s3_uri],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[db-sync] push succeeded", flush=True)
        return True
    print(
        f"[db-sync] push failed (exit {result.returncode}): {result.stderr.strip()}",
        file=sys.stderr,
    )
    return False
