#!/usr/bin/env python3
"""Copy only durable, non-secret runtime history into a cloud data directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from durable_data import (
    DENIED_NAMES,
    DURABLE_EXACT_FILES,
    DURABLE_GLOB_PATTERNS,
    is_durable_data_file,
)

CN = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class SeedEntry:
    relative_path: str
    action: str
    size: int
    sha256: str
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_seed(
    source_dir: Path,
    destination_dir: Path,
    *,
    refresh_existing: bool = False,
    force: bool = False,
) -> list[SeedEntry]:
    """Build a no-side-effect copy plan for allowlisted long-term files."""
    source_dir = Path(source_dir)
    destination_dir = Path(destination_dir)
    if not source_dir.is_dir():
        raise ValueError(f"源数据目录不存在: {source_dir}")

    entries = []
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(source_dir)
        if not is_durable_data_file(relative):
            continue
        digest = sha256_file(source)
        size = source.stat().st_size
        destination = destination_dir / relative
        if not destination.exists():
            action, reason = "copy", "目标不存在"
        elif destination.is_dir():
            action, reason = "skip", "目标是目录"
        else:
            destination_digest = sha256_file(destination)
            if destination_digest == digest:
                action, reason = "skip", "内容一致"
            elif force:
                action, reason = "copy", "显式覆盖"
            elif not refresh_existing:
                action, reason = "skip", "目标已存在；默认不覆盖"
            elif source.stat().st_mtime < destination.stat().st_mtime:
                action, reason = "skip", "目标文件更新时间更晚；核验后可用 --force 覆盖（自动备份）"
            else:
                action, reason = "copy", "源文件更新"
        entries.append(
            SeedEntry(
                relative_path=relative.as_posix(),
                action=action,
                size=size,
                sha256=digest,
                reason=reason,
            )
        )
    return entries


def apply_seed(
    source_dir: Path,
    destination_dir: Path,
    entries: list[SeedEntry],
    *,
    backup: bool = True,
) -> list[SeedEntry]:
    """Apply a plan atomically, preserving a timestamped backup on replacement."""
    source_dir = Path(source_dir)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(CN).strftime("%Y%m%dT%H%M%S")
    applied = []
    for entry in entries:
        if entry.action != "copy":
            applied.append(entry)
            continue
        source = source_dir / entry.relative_path
        target = destination_dir / entry.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and backup:
            backup_path = target.with_name(f"{target.name}.bak-{timestamp}")
            if not backup_path.exists():
                shutil.copy2(target, backup_path)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        applied.append(entry)
    return applied


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步每日简报长期数据到云端运行目录")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--destination-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="实际复制；不加时只预览")
    parser.add_argument("--refresh-existing", action="store_true", help="仅当源文件不旧于目标时更新")
    parser.add_argument("--force", action="store_true", help="覆盖内容不同的目标文件（仍做备份）")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)

    try:
        entries = plan_seed(
            args.source_dir,
            args.destination_dir,
            refresh_existing=args.refresh_existing,
            force=args.force,
        )
        if args.apply:
            entries = apply_seed(
                args.source_dir,
                args.destination_dir,
                entries,
                backup=not args.no_backup,
            )
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2

    copied = [entry for entry in entries if entry.action == "copy"]
    payload = {
        "schema_version": 1,
        "status": "ok",
        "applied": bool(args.apply),
        "source_dir": str(args.source_dir),
        "destination_dir": str(args.destination_dir),
        "summary": {
            "copy": len(copied),
            "skip": len(entries) - len(copied),
        },
        "allowlist": {
            "exact_files": sorted(DURABLE_EXACT_FILES),
            "glob_patterns": list(DURABLE_GLOB_PATTERNS),
            "excluded": sorted(DENIED_NAMES | {"*_today.json", "*cookies*.json"}),
        },
        "entries": [entry.as_dict() for entry in entries],
    }
    if args.manifest:
        write_manifest(args.manifest, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
