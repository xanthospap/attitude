from __future__ import annotations

import datetime as dt
import re
from pathlib import Path


CDDIS_ORBITS_BASE_URL = "https://cddis.nasa.gov/archive/doris/products/orbits"
IGN_ORBITS_HOST = "doris.ign.fr"
IGN_ORBITS_BASE_PATH = "/pub/doris/products/orbits"
IGN_ORBITS_BASE_URL = "ftp://doris.ign.fr/pub/doris/products/orbits"

DEFAULT_ANALYSIS_CENTER = "ssa"


_SP3_RE = re.compile(
    r"^(?P<center>[a-z0-9]{3})"
    r"(?P<satellite>[a-z0-9]{3})"
    r"(?P<version>\d{2})"
    r"\.b(?P<begin_year>\d{2})(?P<begin_doy>\d{3})"
    r"\.e(?P<end_year>\d{2})(?P<end_doy>\d{3})"
    r"\.(?P<dgs>[dg_sDG_S]{3})"
    r"\.sp3"
    r"\.(?P<revision>\d{3})"
    r"\.Z$",
    re.IGNORECASE,
)


def yy_to_year(yy: str | int) -> int:
    """
    Convert two-digit SP3 year to full year.

    DORIS orbit products cover the modern satellite era, so:
        92 -> 1992
        24 -> 2024
    """

    yy = int(yy)

    if yy >= 80:
        return 1900 + yy

    return 2000 + yy


def yy_doy_to_datetime(yy: str | int, doy: str | int) -> dt.datetime:
    year = yy_to_year(yy)
    return dt.datetime(year, 1, 1) + dt.timedelta(days=int(doy) - 1)


def intervals_overlap(
    product_start: dt.datetime,
    product_end: dt.datetime,
    requested_start: dt.datetime,
    requested_end: dt.datetime,
) -> bool:
    return product_start < requested_end and product_end > requested_start


def parse_sp3_filename(filename: str | Path) -> dict | None:
    """
    Parse IDS DORIS SP3 orbit filename.

    Example:
        ssaja320.b16147.e16157.DG_.sp3.001.Z

    Returns a dictionary, or None if the filename does not match.
    """

    name = Path(filename).name
    match = _SP3_RE.match(name)

    if match is None:
        return None

    parts = match.groupdict()

    start = yy_doy_to_datetime(parts["begin_year"], parts["begin_doy"])

    # The filename gives the last day with positions. Treat it as inclusive
    # and convert to a half-open interval by adding one day.
    end = yy_doy_to_datetime(parts["end_year"], parts["end_doy"]) + dt.timedelta(days=1)

    return {
        "filename": name,
        "center": parts["center"].lower(),
        "satellite": parts["satellite"].lower(),
        "version": parts["version"],
        "start": start,
        "end": end,
        "dgs": parts["dgs"].upper(),
        "revision": int(parts["revision"]),
    }


def sp3_overlaps_range(
    filename: str | Path,
    start: dt.datetime,
    end: dt.datetime,
) -> bool:
    info = parse_sp3_filename(filename)

    if info is None:
        return False

    return intervals_overlap(info["start"], info["end"], start, end)


def select_sp3_files(
    filenames: list[str],
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    center: str | None = None,
    version: str | None = None,
) -> list[str]:
    """
    Select SP3 files overlapping [start, end).

    If multiple replacement revisions exist for the same product, keep only
    the highest LLL revision.
    """

    satellite = satellite.lower()
    center = None if center is None else center.lower()

    selected: dict[tuple, dict] = {}

    for filename in filenames:
        info = parse_sp3_filename(filename)

        if info is None:
            continue

        if info["satellite"] != satellite:
            continue

        if center is not None and info["center"] != center:
            continue

        if version is not None and info["version"] != version:
            continue

        if not intervals_overlap(info["start"], info["end"], start, end):
            continue

        key = (
            info["center"],
            info["satellite"],
            info["version"],
            info["start"],
            info["end"],
            info["dgs"],
        )

        current = selected.get(key)

        if current is None or info["revision"] > current["revision"]:
            selected[key] = info

    return [
        info["filename"]
        for info in sorted(
            selected.values(),
            key=lambda item: (
                item["start"],
                item["end"],
                item["center"],
                item["satellite"],
                item["version"],
                item["dgs"],
                item["revision"],
            ),
        )
    ]


def cddis_orbit_directory_url(
    center: str,
    satellite: str,
    base_url: str = CDDIS_ORBITS_BASE_URL,
) -> str:
    return f"{base_url.rstrip('/')}/{center.lower()}/{satellite.lower()}"


def cddis_orbit_url(
    center: str,
    satellite: str,
    filename: str,
    base_url: str = CDDIS_ORBITS_BASE_URL,
) -> str:
    return f"{cddis_orbit_directory_url(center, satellite, base_url)}/{filename}"


def ign_orbit_directory_path(center: str, satellite: str) -> str:
    return f"{IGN_ORBITS_BASE_PATH}/{center.lower()}/{satellite.lower()}"


def ign_orbit_url(
    center: str,
    satellite: str,
    filename: str,
    base_url: str = IGN_ORBITS_BASE_URL,
) -> str:
    return f"{base_url.rstrip('/')}/{center.lower()}/{satellite.lower()}/{filename}"
