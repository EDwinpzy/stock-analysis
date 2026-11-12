#!/usr/bin/env python3
"""Compare local and cloud collector outputs without hiding data differences."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any, Iterable


DYNAMIC_KEYS = {
    "build_time",
    "elapsed_seconds",
    "fetch_time",
    "generated_at",
    "run_time",
    "runtime",
}
UNORDERED_LIST_KEYS = {"columns", "keys"}


def _path_text(path: Iterable[str | int]) -> str:
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        elif text:
            text += f".{part}"
        else:
            text = str(part)
    return text or "$"


def _is_dynamic(key: str, path: tuple[str | int, ...], ignored: set[str]) -> bool:
    current = _path_text((*path, key))
    return key in DYNAMIC_KEYS or current in ignored


def _is_unordered_list(key: str | int, path: tuple[str | int, ...]) -> bool:
    if isinstance(key, int):
        parent = path[-1] if path else ""
        return str(parent).endswith("_columns")
    return key.endswith("_columns") or key in UNORDERED_LIST_KEYS


def compare_json(
    local: Any,
    cloud: Any,
    *,
    ignored_paths: Iterable[str] = (),
) -> list[dict[str, Any]]:
    ignored = set(ignored_paths)
    differences: list[dict[str, Any]] = []

    def visit(left: Any, right: Any, path: tuple[str | int, ...], key: str | int) -> None:
        if isinstance(key, str) and _is_dynamic(key, path, ignored):
            return
        current_path = _path_text(path)
        if current_path in ignored:
            return
        if type(left) is not type(right):
            differences.append(
                {
                    "path": current_path,
                    "kind": "type",
                    "local": type(left).__name__,
                    "cloud": type(right).__name__,
                }
            )
            return
        if isinstance(left, dict):
            left_keys = set(left)
            right_keys = set(right)
            for child in sorted(left_keys - right_keys):
                differences.append(
                    {
                        "path": _path_text((*path, child)),
                        "kind": "missing_in_cloud",
                    }
                )
            for child in sorted(right_keys - left_keys):
                differences.append(
                    {
                        "path": _path_text((*path, child)),
                        "kind": "missing_in_local",
                    }
                )
            for child in sorted(left_keys & right_keys):
                visit(left[child], right[child], (*path, child), child)
            return
        if isinstance(left, list):
            if len(left) != len(right):
                differences.append(
                    {
                        "path": current_path,
                        "kind": "length",
                        "local": len(left),
                        "cloud": len(right),
                    }
                )
            if _is_unordered_list(key, path):
                left_values = sorted(left, key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True))
                right_values = sorted(right, key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True))
                for index, (left_item, right_item) in enumerate(zip(left_values, right_values)):
                    visit(left_item, right_item, (*path, f"sorted:{index}"), index)
                return
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                visit(left_item, right_item, (*path, index), index)
            return
        if left != right:
            differences.append(
                {
                    "path": current_path,
                    "kind": "value",
                    "local": left,
                    "cloud": right,
                }
            )

    visit(local, cloud, (), "")
    return differences


def _fetch_time(data: Any) -> str:
    if isinstance(data, dict):
        value = data.get("fetch_time")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def compare_html(
    local_path: Path,
    cloud_path: Path,
    *,
    local_timestamp: str = "",
    cloud_timestamp: str = "",
) -> dict[str, Any]:
    local_text = local_path.read_text(encoding="utf-8")
    cloud_text = cloud_path.read_text(encoding="utf-8")
    if local_timestamp:
        local_text = local_text.replace(local_timestamp, "<fetch_time>")
    if cloud_timestamp:
        cloud_text = cloud_text.replace(cloud_timestamp, "<fetch_time>")
    if local_text == cloud_text:
        return {"ok": True, "differences": []}
    changes = list(
        difflib.unified_diff(
            local_text.splitlines(),
            cloud_text.splitlines(),
            fromfile=str(local_path),
            tofile=str(cloud_path),
            lineterm="",
        )
    )
    return {
        "ok": False,
        "differences": [{"kind": "html", "diff": changes[:200]}],
    }


def compare_payload(args: argparse.Namespace) -> dict[str, Any]:
    local_data = json.loads(Path(args.data_local).read_text(encoding="utf-8"))
    cloud_data = json.loads(Path(args.data_cloud).read_text(encoding="utf-8"))
    differences = compare_json(
        local_data,
        cloud_data,
        ignored_paths=args.ignore_path,
    )
    payload: dict[str, Any] = {
        "ok": not differences,
        "data": {
            "local": str(Path(args.data_local).resolve()),
            "cloud": str(Path(args.data_cloud).resolve()),
            "difference_count": len(differences),
            "differences": differences,
        },
    }
    if bool(args.html_local) != bool(args.html_cloud):
        payload["ok"] = False
        payload["error"] = "--html-local 和 --html-cloud 必须同时提供"
        return payload
    if args.html_local and args.html_cloud:
        html_result = compare_html(
            Path(args.html_local).resolve(),
            Path(args.html_cloud).resolve(),
            local_timestamp=_fetch_time(local_data),
            cloud_timestamp=_fetch_time(cloud_data),
        )
        payload["html"] = html_result
        payload["ok"] = payload["ok"] and html_result["ok"]
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验本机与云端的个股/行业采集数据及 HTML 是否一致"
    )
    parser.add_argument("--data-local", required=True)
    parser.add_argument("--data-cloud", required=True)
    parser.add_argument("--html-local", default="")
    parser.add_argument("--html-cloud", default="")
    parser.add_argument(
        "--ignore-path",
        action="append",
        default=[],
        help="额外忽略的 JSON 路径，例如 quote.vendor_time",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = compare_payload(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
