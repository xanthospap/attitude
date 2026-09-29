from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sources.files import download_to_path
from sources.satmass import satmass_filename, satmass_url


def filename_from_url(url: str) -> str:
    filename = Path(urlparse(url).path).name

    if not filename:
        raise ValueError(f"Could not infer filename from URL: {url}")

    return filename


def download_file(
    url: str,
    output_dir: str | Path,
    filename: str | None = None,
    overwrite: bool = False,
    timeout: float = 60.0,
) -> Path:
    """
    Download a file from IDS.

    IDS satellite mass files are served over FTP.
    """

    output_file = Path(output_dir) / (filename or filename_from_url(url))
    return download_to_path(
        url,
        output_file,
        overwrite=overwrite,
        timeout=timeout,
    )


def download_satmass(
    satellite: str,
    output_dir: str | Path,
    overwrite: bool = False,
) -> Path:
    url = satmass_url(satellite)

    return download_file(
        url=url,
        output_dir=output_dir,
        filename=satmass_filename(satellite),
        overwrite=overwrite,
    )
