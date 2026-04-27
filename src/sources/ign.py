from __future__ import annotations

import logging
import shutil
import subprocess
from ftplib import FTP
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from sources.rinex import rinex_urls_for_range
from sources.orbits import (
    IGN_ORBITS_HOST,
    ign_orbit_directory_path,
    ign_orbit_url,
    select_sp3_files,
)


logger = logging.getLogger(__name__)


def filename_from_url(url: str) -> str:
    filename = Path(urlparse(url).path).name

    if not filename:
        raise ValueError(f"Could not infer filename from URL: {url}")

    return filename


def download_file(
    url: str,
    output_dir: str | Path,
    overwrite: bool = False,
    timeout: float = 60.0,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename_from_url(url)

    if output_file.exists() and not overwrite:
        logger.info("Using existing file %s", output_file)
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    logger.info("Downloading %s", url)

    with urlopen(url, timeout=timeout) as response:
        with tmp_file.open("wb") as fout:
            shutil.copyfileobj(response, fout)

    tmp_file.replace(output_file)

    return output_file


def uncompress_z_file(
    compressed_file: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    Uncompress a Unix .Z file.

    Python's stdlib does not read old Unix compress/LZW .Z files directly,
    so use an external tool. GNU gzip can usually decompress .Z files.

    Returns the uncompressed file path.
    """

    compressed_file = Path(compressed_file)

    if compressed_file.suffix != ".Z":
        return compressed_file

    output_file = compressed_file.with_suffix("")

    if output_file.exists() and not overwrite:
        logger.info("Using existing uncompressed file %s", output_file)
        return output_file

    if shutil.which("gzip") is not None:
        command = ["gzip", "-d", "-f", str(compressed_file)]
    elif shutil.which("uncompress") is not None:
        command = ["uncompress", "-f", str(compressed_file)]
    else:
        raise RuntimeError(
            "Cannot uncompress .Z file: neither 'gzip' nor 'uncompress' "
            "was found on PATH."
        )

    logger.info("Uncompressing %s", compressed_file)
    subprocess.run(command, check=True)

    return output_file


def download_rinex(
    satellite: str,
    start,
    end,
    output_dir: str | Path,
    overwrite: bool = False,
    uncompress: bool = False,
) -> list[Path]:
    """
    Download DORIS RINEX files from IGN for the requested datetime range.
    """

    urls = rinex_urls_for_range(
        satellite=satellite,
        start=start,
        end=end,
        source="ign",
    )

    files: list[Path] = []

    for url in urls:
        try:
            downloaded = download_file(
                url=url,
                output_dir=output_dir,
                overwrite=overwrite,
            )

            if uncompress:
                downloaded = uncompress_z_file(
                    downloaded,
                    overwrite=overwrite,
                )

            files.append(downloaded)

        except Exception as exc:
            logger.error("Failed to download %s: %s", url, exc)

    return files


def list_ftp_directory(
    host: str,
    directory: str,
    user: str = "anonymous",
    password: str = "anonymous@",
    timeout: float = 60.0,
) -> list[str]:
    """
    Return filenames from an FTP directory.
    """

    with FTP(host, timeout=timeout) as ftp:
        ftp.login(user=user, passwd=password)
        ftp.cwd(directory)
        names = ftp.nlst()

    return [Path(name).name for name in names if Path(name).name]


def download_url(
    url: str,
    output_dir: str | Path,
    overwrite: bool = False,
    timeout: float = 60.0,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename_from_url(url)

    if output_file.exists() and not overwrite:
        logger.info("Using existing file %s", output_file)
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    logger.info("Downloading %s", url)

    with urlopen(url, timeout=timeout) as response:
        with tmp_file.open("wb") as fout:
            shutil.copyfileobj(response, fout)

    tmp_file.replace(output_file)

    return output_file


def find_orbit_urls(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    center: str = "ssa",
    version: str | None = None,
    user: str = "anonymous",
    password: str = "anonymous@",
) -> list[str]:
    """
    List the IGN orbit directory and return SP3 files overlapping [start, end).
    """

    directory = ign_orbit_directory_path(
        center=center,
        satellite=satellite,
    )

    filenames = list_ftp_directory(
        host=IGN_ORBITS_HOST,
        directory=directory,
        user=user,
        password=password,
    )

    selected = select_sp3_files(
        filenames=filenames,
        satellite=satellite,
        start=start,
        end=end,
        center=center,
        version=version,
    )

    return [
        ign_orbit_url(
            center=center,
            satellite=satellite,
            filename=filename,
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
    uncompress: bool = False,
    user: str = "anonymous",
    password: str = "anonymous@",
) -> list[Path]:
    """
    Download IGN SP3 orbit files overlapping [start, end).
    """

    urls = find_orbit_urls(
        satellite=satellite,
        start=start,
        end=end,
        center=center,
        version=version,
        user=user,
        password=password,
    )

    files: list[Path] = []

    for url in urls:
        try:
            downloaded = download_url(
                url=url,
                output_dir=output_dir,
                overwrite=overwrite,
            )

            if uncompress:
                downloaded = uncompress_z_file(
                    downloaded,
                    overwrite=overwrite,
                )

            files.append(downloaded)

        except Exception as exc:
            logger.error("Failed to download %s: %s", url, exc)

    return files
