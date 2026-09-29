from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from pathlib import Path
from typing import Any

import yaml


KNOWN_SATELLITES = {
    "cs2", "en1", "h2a", "h2c", "h2d", "ja1", "ja2", "ja3",
    "s3a", "s3b", "s3c", "s6a", "s6b", "sp2", "sp3", "sp4",
    "sp5", "srl", "swo", "top",
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader which rejects duplicate mapping keys."""


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = key_node.start_mark
            raise ValueError(
                f"duplicate YAML key {key!r} at line {mark.line + 1}, "
                f"column {mark.column + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = yaml.load(stream, Loader=UniqueKeyLoader) or {}
    if not isinstance(value, dict):
        raise ValueError("the YAML document root must be a mapping")
    return value


def mapping_if_present(config: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"YAML option {key!r} must be a mapping")
    return value


def resolve_path(value: Any, root: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else root / path


def parse_utc_datetime(value: Any) -> dt.datetime:
    """Parse a user epoch and return a naive UTC datetime.

    Naive YAML/CLI values are defined to be UTC.  Offset-aware values are
    converted to UTC.  This avoids interpreting input in the host timezone.
    """
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time())
    elif value is None:
        raise ValueError("missing datetime value")
    else:
        text = str(value).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(text)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed


def analysis_interval(config: dict[str, Any]) -> tuple[dt.datetime, dt.datetime]:
    rinex = mapping_if_present(config, "rinex")
    if rinex is None or rinex.get("from") is None or rinex.get("to") is None:
        raise ValueError("rinex.from and rinex.to are required to determine the interval")
    start = parse_utc_datetime(rinex["from"])
    stop = parse_utc_datetime(rinex["to"])
    if stop <= start:
        raise ValueError(f"rinex.to must be after rinex.from: {start} -> {stop}")
    return start, stop


def satellite_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only the per-satellite YAML entries needed by downloaders."""
    raw = config.get("satellite-attitude")
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("satellite-attitude must be a mapping or sequence")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"satellite-attitude[{index}] must be a mapping")
        satellite = str(item.get("satellite", "")).strip().lower()
        if not satellite:
            raise ValueError(f"satellite-attitude[{index}] has no satellite")
        if satellite not in KNOWN_SATELLITES:
            raise ValueError(f"unknown satellite identifier {satellite!r}")
        if satellite in seen:
            raise ValueError(f"duplicate satellite entry {satellite!r}")
        seen.add(satellite)
        copied = dict(item)
        copied["satellite"] = satellite
        entries.append(copied)
    return entries


@dataclass(frozen=True)
class PreparationContext:
    config: dict[str, Any]
    root: Path
    start: dt.datetime
    stop: dt.datetime
    satellites: list[dict[str, Any]]
    overwrite: bool = False
    decompress: bool = True
    attitude_s3cfg: Path | None = None
    attitude_user: str | None = None
    attitude_password: str | None = None


def make_context(
    config: dict[str, Any],
    root: str | Path,
    *,
    overwrite: bool = False,
    decompress: bool = True,
    attitude_s3cfg: str | Path | None = None,
    attitude_user: str | None = None,
    attitude_password: str | None = None,
) -> PreparationContext:
    start, stop = analysis_interval(config)
    return PreparationContext(
        config=config,
        root=Path(root).expanduser().resolve(),
        start=start,
        stop=stop,
        satellites=satellite_entries(config),
        overwrite=overwrite,
        decompress=decompress,
        attitude_s3cfg=None if attitude_s3cfg is None else Path(attitude_s3cfg).expanduser(),
        attitude_user=attitude_user,
        attitude_password=attitude_password,
    )
