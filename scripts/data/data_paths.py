"""共有データパス解決ヘルパー（正本: research-template、sync で配布）。

台帳: docs/data/data-paths.json（説明は docs/data/data-catalog.md）。

使い方::

    from scripts.data.data_paths import data_path, list_keys

    acc = data_path("fq_accounting_exp")   # -> Path（存在しなければ FileNotFoundError）
    acc = data_path("fq_accounting_exp", must_exist=False)

ルートは環境変数で上書きできる（WSL / 別マシン用）:
RESEARCH_ONEDRIVE_ROOT / RESEARCH_DESKTOP_ROOT / RESEARCH_PROJECT_ROOT
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_JSON = _REPO_ROOT / "docs" / "data" / "data-paths.json"


@lru_cache(maxsize=1)
def _registry() -> dict:
    with open(_REGISTRY_JSON, encoding="utf-8") as f:
        return json.load(f)


def root_path(name: str) -> Path:
    """ルート名（onedrive / desktop / project）を Path に解決する。"""
    roots = _registry()["roots"]
    if name not in roots:
        raise KeyError(f"unknown root: {name!r} (available: {sorted(roots)})")
    spec = roots[name]
    override = os.environ.get(spec["env"])
    if override:
        return Path(override).expanduser()
    return Path(spec["default"]).expanduser()


def data_path(key: str, must_exist: bool = True) -> Path:
    """台帳キーを絶対パスに解決する。"""
    entries = _registry()["entries"]
    if key not in entries:
        raise KeyError(
            f"unknown data key: {key!r}. list_keys() で一覧を確認してください。"
        )
    entry = entries[key]
    path = root_path(entry["root"]) / entry["path"]
    if must_exist and not path.exists():
        raise FileNotFoundError(
            f"{key}: {path} が見つかりません。OneDrive 未同期またはルートの"
            f"上書き（{_registry()['roots'][entry['root']]['env']}）を確認してください。"
        )
    return path


def describe(key: str) -> str:
    """キーの説明文を返す。"""
    return _registry()["entries"][key]["desc"]


def list_keys() -> list[str]:
    """登録済みキーの一覧。"""
    return sorted(_registry()["entries"])


if __name__ == "__main__":
    for k in list_keys():
        p = data_path(k, must_exist=False)
        mark = "OK" if p.exists() else "--"
        print(f"[{mark}] {k}: {p}")
