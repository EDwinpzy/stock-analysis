"""Persistent runtime-data locations for Daily Briefing Pro."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping


def _copy_missing_files(source: Path, destination: Path) -> None:
    """Copy a tree without replacing existing files, publishing each file atomically."""
    if not source.is_dir():
        return

    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    # A configured data directory inside a source tree must not be walked recursively.
    if source_resolved == destination_resolved or source_resolved in destination_resolved.parents:
        return

    for source_file in sorted(source.rglob("*")):
        if source_file.is_symlink() or not source_file.is_file():
            continue

        target = destination / source_file.relative_to(source)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temp_file = Path(temp_name)
        try:
            shutil.copy2(source_file, temp_file)
            try:
                if os.name == "nt":
                    # Windows rename is atomic and fails if another process created target.
                    os.rename(temp_file, target)
                else:
                    # A hard link atomically creates target only when it is still absent.
                    os.link(temp_file, target)
            except FileExistsError:
                pass
        finally:
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass


def get_data_dir(
    package_dir: Path,
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return the durable runtime-data directory and migrate missing legacy files once.

    Existing files in the durable directory always win. Migration checks the former
    stable skill location first, then fills remaining gaps from this package version.
    """
    package_dir = Path(package_dir)
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)

    override = env.get("DAILY_BRIEFING_DATA_DIR")
    data_dir = Path(override).expanduser() if override else (
        home / ".codex" / "daily-briefing-pro" / "data"
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    legacy_data_dir = home / ".agents" / "skills" / "daily-briefing-pro" / "data"
    _copy_missing_files(legacy_data_dir, data_dir)
    _copy_missing_files(package_dir / "data", data_dir)
    return data_dir
