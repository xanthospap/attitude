from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import requests
from opnieuw import retry

from sources.attitude import product_overlaps_range, years_to_scan_for_range

from sources.orbits import (
    CDDIS_ORBITS_BASE_URL,
    cddis_orbit_directory_url,
    cddis_orbit_url,
    select_sp3_files,
)


logger = logging.getLogger(__name__)


@retry(
    retry_on_exceptions=(
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
        requests.exceptions.Timeout,
    ),
    max_calls_total=4,
    retry_window_after_first_call_in_seconds=60,
)
def list_directory(url: str, timeout: float = 60.0) -> list[str]:
    """
    Return filenames from a CDDIS directory listing.

    CDDIS supports the `*?list` suffix.
    """

    url = url.rstrip("/")
    response = requests.get(f"{url}/*?list", timeout=timeout)
    response.raise_for_status()

    filenames: list[str] = []

    for line in response.text.splitlines():
        line = line.strip()

        if not line:
            continue

        filenames.append(line.split()[0])

    return filenames


def attitude_year_url(base_url: str, satellite: str, year: int) -> str:
    return f"{base_url.rstrip('/')}/{satellite.lower()}/{year:04d}"


def find_attitude_urls(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    base_url: str,
    data_types: list[str] | tuple[str, ...],
) -> list[str]:
    """
    Find CDDIS attitude files whose validity interval overlaps [start, end).
    """

    satellite = satellite.lower()
    urls: list[str] = []

    for year in years_to_scan_for_range(start, end):
        directory_url = attitude_year_url(base_url, satellite, year)

        try:
            filenames = list_directory(directory_url)
        except requests.exceptions.RequestException as exc:
            logger.warning("Could not list CDDIS directory %s: %s", directory_url, exc)
            continue

        for filename in filenames:
            filename_lower = filename.lower()

            if not filename_lower.startswith(satellite):
                continue

            if not any(data_type in filename_lower for data_type in data_types):
                continue

            if not product_overlaps_range(filename, start, end):
                continue

            urls.append(f"{directory_url}/{filename}")

    return sorted(set(urls))


@retry(
    retry_on_exceptions=(
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
        requests.exceptions.Timeout,
    ),
    max_calls_total=4,
    retry_window_after_first_call_in_seconds=60,
)
def download_url(
    url: str,
    output_dir: str | Path,
    overwrite: bool = False,
    timeout: float = 60.0,
    chunk_size: int = 1024 * 1024,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / url.rstrip("/").split("/")[-1]

    if output_file.exists() and not overwrite:
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()

        with tmp_file.open("wb") as fout:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fout.write(chunk)

    tmp_file.replace(output_file)

    return output_file


def download_attitude(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    output_dir: str | Path,
    base_url: str,
    data_types: list[str] | tuple[str, ...],
    overwrite: bool = False,
) -> list[Path]:
    """
    Download CDDIS attitude files overlapping [start, end).
    """

    urls = find_attitude_urls(
        satellite=satellite,
        start=start,
        end=end,
        base_url=base_url,
        data_types=data_types,
    )

    files: list[Path] = []

    for url in urls:
        try:
            files.append(
                download_url(
                    url=url,
                    output_dir=output_dir,
                    overwrite=overwrite,
                )
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to download %s: %s", url, exc)

    return files


def find_orbit_urls(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    center: str = "ssa",
    version: str | None = None,
    base_url: str = CDDIS_ORBITS_BASE_URL,
) -> list[str]:
    """
    List the CDDIS orbit directory and return SP3 files overlapping [start, end).
    """

    directory_url = cddis_orbit_directory_url(
        center=center,
        satellite=satellite,
        base_url=base_url,
    )

    filenames = list_directory(directory_url)

    selected = select_sp3_files(
        filenames=filenames,
        satellite=satellite,
        start=start,
        end=end,
        center=center,
        version=version,
    )

    return [
        cddis_orbit_url(
            center=center,
            satellite=satellite,
            filename=filename,
            base_url=base_url,
        )
        for filename in selected
    ]


def download_orbits(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    output_dir: str | Path,
    center: str = "ssa",
    version: str | None = None,
    overwrite: bool = False,
    base_url: str = CDDIS_ORBITS_BASE_URL,
) -> list[Path]:
    """
    Download CDDIS SP3 orbit files overlapping [start, end).

    CDDIS access usually requires Earthdata credentials configured outside this
    function, e.g. via .netrc/cookies depending on the user's setup.
    """

    urls = find_orbit_urls(
        satellite=satellite,
        start=start,
        end=end,
        center=center,
        version=version,
        base_url=base_url,
    )

    files: list[Path] = []

    for url in urls:
        try:
            files.append(
                download_url(
                    url=url,
                    output_dir=output_dir,
                    overwrite=overwrite,
                )
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to download %s: %s", url, exc)

    return files
