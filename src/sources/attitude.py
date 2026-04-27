from __future__ import annotations

import datetime as dt
import re
from pathlib import Path


SATELLITE_INFO = {
    "ja1": {
        "name": "Jason-1",
        "source": "cddis",
        "launch_year": 2001,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "ja2": {
        "name": "Jason-2",
        "source": "cddis",
        "launch_year": 2008,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "ja3": {
        "name": "Jason-3",
        "source": "cddis",
        "launch_year": 2016,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "s3a": {
        "name": "Sentinel-3A",
        "source": "copernicus",
        "launch_year": 2016,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
    "s3b": {
        "name": "Sentinel-3B",
        "source": "copernicus",
        "launch_year": 2018,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
    "s6a": {
        "name": "Sentinel-6A",
        "source": "copernicus",
        "launch_year": 2020,
        "base_url": "Sentinel-6/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
    "swo": {
        "name": "SWOT",
        "source": "ign",
        "launch_year": 2023,
        "base_url": "pub/doris/ancillary/quaternions/swo",
        "data_types": ["qbody", "qsolp"],
    },
}


def dates_touched_by_range(start: dt.datetime, end: dt.datetime) -> list[dt.date]:
    """
    Return all calendar dates touched by [start, end).

    Example:
        2024-01-01T12:00 to 2024-01-03T03:00
        -> 2024-01-01, 2024-01-02, 2024-01-03
    """

    if end <= start:
        raise ValueError("End datetime must be after start datetime")

    first = start.date()
    last = (end - dt.timedelta(microseconds=1)).date()

    ndays = (last - first).days + 1

    return [first + dt.timedelta(days=i) for i in range(ndays)]


def split_dates_by_year(dates: list[dt.date]) -> list[list[dt.date]]:
    return [
        [date for date in dates if date.year == year]
        for year in sorted({date.year for date in dates})
    ]


def date_ranges_for_datetime_range(
    start: dt.datetime,
    end: dt.datetime,
) -> list[list[dt.date]]:
    return split_dates_by_year(dates_touched_by_range(start, end))


def intervals_overlap(
    product_start: dt.datetime,
    product_end: dt.datetime,
    requested_start: dt.datetime,
    requested_end: dt.datetime,
) -> bool:
    """
    Half-open interval overlap test.

    Product belongs to request if:
        [product_start, product_end) overlaps [requested_start, requested_end)
    """

    return product_start < requested_end and product_end > requested_start


def parse_product_range(filename: str | Path) -> tuple[dt.datetime, dt.datetime] | None:
    """
    Parse product validity start/end from known attitude product names.

    Supports names containing:
        YYYYMMDDHHMMSS_YYYYMMDDHHMMSS
        YYYYMMDDTHHMMSS_YYYYMMDDTHHMMSS
        YYYYMMDDTHHMMSS_YYYYMMDDTHHMMSS.SAFE
    """

    name = Path(filename).name

    match = re.search(
        r"(\d{8}T?\d{6})_(\d{8}T?\d{6})",
        name,
    )

    if match is None:
        return None

    start_raw, end_raw = match.groups()

    def parse(value: str) -> dt.datetime:
        if "T" in value:
            return dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
        return dt.datetime.strptime(value, "%Y%m%d%H%M%S")

    return parse(start_raw), parse(end_raw)


def product_overlaps_range(
    filename: str | Path,
    requested_start: dt.datetime,
    requested_end: dt.datetime,
) -> bool:
    product_range = parse_product_range(filename)

    if product_range is None:
        return False

    product_start, product_end = product_range

    return intervals_overlap(
        product_start=product_start,
        product_end=product_end,
        requested_start=requested_start,
        requested_end=requested_end,
    )


def dates_to_scan_for_range(
    start: dt.datetime,
    end: dt.datetime,
    pad_days: int = 1,
) -> list[dt.date]:
    """
    Return calendar dates to inspect remotely.

    We intentionally scan a small padded range because a product can start
    before the requested interval but still overlap it.
    """

    return dates_touched_by_range(
        start - dt.timedelta(days=pad_days),
        end + dt.timedelta(days=pad_days),
    )


def years_to_scan_for_range(
    start: dt.datetime,
    end: dt.datetime,
    pad_days: int = 1,
) -> list[int]:
    return sorted(
        {
            date.year
            for date in dates_to_scan_for_range(
                start=start,
                end=end,
                pad_days=pad_days,
            )
        }
    )
