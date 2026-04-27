from __future__ import annotations

import datetime as dt
from pathlib import Path


IGN_DORIS_DATA_BASE = "ftp://doris.ign.fr/pub/doris/data"
CDDIS_DORIS_DATA_BASE = "https://cddis.nasa.gov/archive/doris/data"


def dates_touched_by_range(start: dt.datetime, end: dt.datetime) -> list[dt.date]:
    """
    Return all calendar dates touched by [start, end).

    DORIS RINEX files have 1-day validity, so a datetime range maps directly
    to the dates it touches.
    """

    if end <= start:
        raise ValueError("End datetime must be after start datetime")

    first = start.date()
    last = (end - dt.timedelta(microseconds=1)).date()

    ndays = (last - first).days + 1

    return [first + dt.timedelta(days=i) for i in range(ndays)]


def rinex_filename(satellite: str, date: dt.date) -> str:
    """
    Return DORIS RINEX filename.

    Format:
        SSSrxYYDDD.001.Z

    Example:
        ja3rx24104.001.Z
    """

    satellite = satellite.lower()
    yy = date.strftime("%y")
    doy = date.strftime("%j")

    return f"{satellite}rx{yy}{doy}.001.Z"


def rinex_relative_path(satellite: str, date: dt.date) -> str:
    """
    Return source-relative RINEX path.

    Format:
        SSS/YYYY/SSSrxYYDDD.001.Z
    """

    satellite = satellite.lower()

    return f"{satellite}/{date.year:04d}/{rinex_filename(satellite, date)}"


def ign_rinex_url(satellite: str, date: dt.date) -> str:
    return f"{IGN_DORIS_DATA_BASE}/{rinex_relative_path(satellite, date)}"


def cddis_rinex_url(satellite: str, date: dt.date) -> str:
    return f"{CDDIS_DORIS_DATA_BASE}/{rinex_relative_path(satellite, date)}"


def local_rinex_path(
    satellite: str,
    date: dt.date,
    output_dir: str | Path,
) -> Path:
    """
    Keep local files flat for now.

    Example:
        data/sworx24002.001.Z
    """

    return Path(output_dir) / rinex_filename(satellite, date)


def rinex_urls_for_range(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    source: str = "ign",
) -> list[str]:
    source = source.lower()

    urls = []

    for date in dates_touched_by_range(start, end):
        if source == "ign":
            urls.append(ign_rinex_url(satellite, date))
        elif source == "cddis":
            urls.append(cddis_rinex_url(satellite, date))
        else:
            raise ValueError(f"Unsupported RINEX source: {source}")

    return urls
