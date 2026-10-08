#!/usr/bin/env python3
"""将浏览器导出的抖音 Cookie 文本转换为 Playwright cookie JSON，不回显会话值。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def _expires(raw: str):
    raw = str(raw or "").strip()
    if not raw or raw in {"会话", "Session"}:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return None


def convert(source: Path) -> list[dict]:
    cookies = []
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 5:
            continue
        name, value, domain, path, expires_raw = cols[:5]
        name, domain, path = name.strip(), domain.strip(), path.strip() or "/"
        if not name or not domain:
            continue
        item = {"name": name, "value": value, "domain": domain, "path": path}
        expires = _expires(expires_raw)
        if expires:
            item["expires"] = expires
        # Chrome 导出列：第6列 httpOnly、第7列 secure。
        item["httpOnly"] = len(cols) > 6 and cols[6].strip() == "✓"
        item["secure"] = len(cols) > 7 and cols[7].strip() == "✓"
        cookies.append(item)
    return cookies


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("用法：python import_douyin_cookie_text.py 输入文本 输出JSON")
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    cookies = convert(source)
    if not cookies:
        raise SystemExit("未解析到有效 Cookie")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导入 {len(cookies)} 个 Cookie（未回显会话值）")


if __name__ == "__main__":
    main()
