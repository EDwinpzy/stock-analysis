"""Persistent runtime-data locations for Daily Briefing Pro."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from durable_data import is_durable_data_file


def _copy_missing_files(source: Path, destination: Path) -> None:
    """Copy allowlisted durable files without replacing existing files."""
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
        relative = source_file.relative_to(source)
        if not is_durable_data_file(relative):
            continue

        target = destination / relative
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
    """Return the durable runtime-data directory and seed missing package inputs.

    Existing files always win. Missing long-lived model/cache inputs may be seeded
    from the package, while snapshots, cookies, and temporary quote HTML never enter
    a clean runtime. No legacy installation directory is scanned.
    """
    package_dir = Path(package_dir)
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)

    override = env.get("DAILY_BRIEFING_DATA_DIR")
    data_dir = Path(override).expanduser() if override else (
        home / ".codex" / "daily-briefing-pro" / "data"
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    # Missing-only: a clean cloud task starts from the shipped baseline, while
    # refreshed runtime files always win. Snapshots/cookies are filtered out by
    # the durable allowlist, so this cannot resurrect *_today.json state.
    _copy_missing_files(package_dir / "data", data_dir)
    return data_dir
