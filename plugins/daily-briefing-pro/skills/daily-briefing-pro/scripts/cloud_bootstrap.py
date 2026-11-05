"""Self-contained runtime bootstrap for clean (cloud) installs.

The marketplace plugin ships only the skill tree, so a clean cloud task has no
durable history and no rotation model.  This module restores the curated
baseline shipped under ``data/cloud-baseline``:

* durable JSON/CSV history is copied missing-only into the runtime data dir;
* the rotation model archive is extracted once into a writable versioned
  directory, so the collector can refresh it without touching the package.

Nothing is overwritten: an existing runtime file or model always wins.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Mapping

from durable_data import is_durable_data_file

MODEL_ARCHIVE = Path("cloud-baseline") / "models" / "sw_rotation_model.zip"
MODEL_REQUIRED = (
    "run.py",
    "config.json",
    "src/data.py",
    "src/features.py",
    "src/engine.py",
    "data/ths_industry_info.csv",
    "data/ths_industry_daily.csv",
    "data/benchmark_csi300.csv",
)


def baseline_data_dir(package_dir: Path) -> Path:
    # The shipped skill data directory is the curated baseline.
    return Path(package_dir) / "data"


def model_archive_path(package_dir: Path) -> Path:
    return Path(package_dir) / "data" / MODEL_ARCHIVE


def plugin_root(package_dir: Path) -> Path:
    """Return the plugin root that contains ``skills/`` when the path is deep enough."""
    parents = Path(package_dir).parents
    return parents[1] if len(parents) > 1 else Path(package_dir).parent


def model_cache_root(package_dir: Path, data_dir: Path | None = None,
                     env: Mapping[str, str] | None = None) -> Path:
    values = env if env is not None else os.environ
    override = str(values.get("DAILY_BRIEFING_MODEL_CACHE") or "").strip()
    if override:
        return Path(override).expanduser()
    if data_dir is not None:
        return Path(data_dir).parent / "models"
    return plugin_root(package_dir) / "models"


def _copy_missing(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    copied = 0
    for item in sorted(source.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue
        relative = item.relative_to(source)
        if not is_durable_data_file(relative):
            continue
        destination = target / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.close(fd)
        temp = Path(temp_name)
        try:
            shutil.copy2(item, temp)
            try:
                if os.name == "nt":
                    os.rename(temp, destination)
                else:
                    os.link(temp, destination)
            except FileExistsError:
                pass
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
        if destination.exists():
            copied += 1
    return copied


def seed_baseline_data(package_dir: Path, data_dir: Path) -> int:
    """Copy the curated history baseline; existing runtime files always win."""
    return _copy_missing(baseline_data_dir(package_dir), Path(data_dir))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_model_dir(path: Path | None) -> bool:
    return bool(path) and all((Path(path) / name).is_file() for name in MODEL_REQUIRED)


def _candidate_dirs(package_dir: Path, data_dir: Path | None,
                    env: Mapping[str, str]) -> list[Path]:
    candidates: list[Path] = []
    for value in (
        env.get("ROTATION_MODEL_DIR"),
        Path(package_dir) / "models" / "sw_rotation_model",
        Path(package_dir).parent / "models" / "sw_rotation_model",
        plugin_root(package_dir) / "models" / "sw_rotation_model",
    ):
        if value:
            candidates.append(Path(value).expanduser())
    root = model_cache_root(package_dir, data_dir, env)
    if root.is_dir():
        candidates.extend(sorted(root.glob("sw_rotation_model-*")))
        candidates.append(root / "sw_rotation_model")
    return candidates


def _extract(archive: Path, target: Path, expected_sha: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".model-", dir=target.parent))
    try:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                relative = Path(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"模型包包含非法路径: {member.filename}")
            bundle.extractall(work)
        source = work
        entries = list(work.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            source = entries[0]
        if not _is_model_dir(source):
            raise ValueError("模型包缺少 run.py/config.json/原始行情数据")
        for item in source.iterdir():
            shutil.move(str(item), str(target / item.name))
        (target / ".bundle-sha256").write_text(expected_sha, encoding="utf-8")
        (target / "outputs").mkdir(exist_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ensure_rotation_model(package_dir: Path, data_dir: Path | None = None,
                          env: Mapping[str, str] | None = None) -> Path | None:
    """Return a runnable model dir, extracting the bundled archive if needed."""
    values = env if env is not None else os.environ
    package_dir = Path(package_dir)
    for candidate in _candidate_dirs(package_dir, data_dir, values):
        if _is_model_dir(candidate):
            return candidate

    archive = model_archive_path(package_dir)
    if not archive.is_file():
        return None
    expected = _sha256(archive)
    root = model_cache_root(package_dir, data_dir, values)
    target = root / f"sw_rotation_model-{expected[:12]}"
    if _is_model_dir(target):
        return target
    _extract(archive, target, expected)
    return target if _is_model_dir(target) else None


def bootstrap(package_dir: Path, data_dir: Path,
              env: Mapping[str, str] | None = None) -> dict:
    """Seed durable data and materialise the model; never raises for missing assets."""
    result = {"data_seeded": 0, "model_dir": "", "errors": []}
    try:
        result["data_seeded"] = seed_baseline_data(package_dir, data_dir)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"baseline:{type(exc).__name__}:{exc}")
    try:
        model = ensure_rotation_model(package_dir, data_dir, env)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"model:{type(exc).__name__}:{exc}")
    else:
        result["model_dir"] = str(model or "")
    return result
