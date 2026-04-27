from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

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

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / (filename or filename_from_url(url))

    if output_file.exists() and not overwrite:
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    with urlopen(url, timeout=timeout) as response:
        with tmp_file.open("wb") as fout:
            shutil.copyfileobj(response, fout)

    tmp_file.replace(output_file)

    return output_file


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
