from __future__ import annotations

import bz2
import gzip
import logging
import lzma
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile


LOGGER = logging.getLogger(__name__)

COMPRESSION_SUFFIXES = (".gz", ".bz2", ".xz", ".Z", ".zip")


def is_nonempty_file(path: str | Path) -> bool:
    """Return ``True`` only for an existing regular file with nonzero size."""
    candidate = Path(path)
    try:
        return candidate.is_file() and candidate.stat().st_size > 0
    except OSError:
        return False


def compression_suffix(path: str | Path) -> str | None:
    name = str(path)
    for suffix in COMPRESSION_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return None


def uncompressed_path(path: str | Path) -> Path:
    source = Path(path)
    suffix = compression_suffix(source)
    if suffix is None:
        return source
    return Path(str(source)[: -len(suffix)])


def existing_variant(path: str | Path) -> Path | None:
    """Find a nonempty requested, compressed, or uncompressed file variant.

    The exact path is preferred.  This makes repeated runs cheap while allowing
    a previous run to have kept either the archive or its decompressed form.
    """
    requested = Path(path)
    candidates = [requested]
    suffix = compression_suffix(requested)
    if suffix is not None:
        candidates.append(uncompressed_path(requested))
    else:
        candidates.extend(Path(str(requested) + item) for item in COMPRESSION_SUFFIXES)

    for candidate in candidates:
        if is_nonempty_file(candidate):
            return candidate
    return None


def _copy_stream(source, target: Path) -> None:
    temporary = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        if not is_nonempty_file(temporary):
            raise OSError(f"download/decompression produced an empty file: {temporary}")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def decompress_file(
    source: str | Path,
    target: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    """Decompress a single-file gzip, bzip2, xz, Unix-compress, or ZIP file.

    The compressed input is intentionally retained.  ZIP archives must contain
    exactly one regular file; multi-file archives are not product files and are
    rejected rather than extracted ambiguously.
    """
    source_path = Path(source)
    suffix = compression_suffix(source_path)
    if suffix is None:
        return source_path
    if not is_nonempty_file(source_path):
        raise OSError(f"compressed file is missing or empty: {source_path}")

    target_path = Path(target) if target is not None else uncompressed_path(source_path)
    if not overwrite and is_nonempty_file(target_path):
        return target_path

    LOGGER.info("Decompressing %s -> %s", source_path, target_path)
    if suffix == ".gz":
        with gzip.open(source_path, "rb") as stream:
            _copy_stream(stream, target_path)
    elif suffix == ".bz2":
        with bz2.open(source_path, "rb") as stream:
            _copy_stream(stream, target_path)
    elif suffix == ".xz":
        with lzma.open(source_path, "rb") as stream:
            _copy_stream(stream, target_path)
    elif suffix == ".zip":
        with zipfile.ZipFile(source_path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) != 1:
                raise ValueError(
                    f"ZIP product {source_path} contains {len(members)} files; expected one"
                )
            with archive.open(members[0]) as stream:
                _copy_stream(stream, target_path)
    else:  # Unix compress (.Z)
        executable = shutil.which("gzip") or shutil.which("uncompress")
        if executable is None:
            raise RuntimeError(
                "cannot decompress .Z file: install gzip or uncompress"
            )
        command = [executable, "-cd", str(source_path)]
        temporary = target_path.with_name(target_path.name + ".part")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with temporary.open("wb") as output:
                subprocess.run(command, stdout=output, check=True)
            if not is_nonempty_file(temporary):
                raise OSError(f"decompression produced an empty file: {temporary}")
            temporary.replace(target_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    return target_path


def _remote_suffix(url: str) -> str | None:
    return compression_suffix(Path(urlparse(url).path).name)


def download_to_path(
    url: str,
    target: str | Path,
    *,
    overwrite: bool = False,
    decompress: bool = False,
    timeout: float = 60.0,
) -> Path:
    """Download ``url`` to the YAML-selected target name.

    A compressed remote product is first stored beside the requested target
    with its compression suffix.  With ``decompress=True`` the returned path is
    always the requested path; otherwise the compressed path is returned.
    """
    requested = Path(target)
    remote_suffix = _remote_suffix(url)
    requested_suffix = compression_suffix(requested)
    final_target = (
        uncompressed_path(requested)
        if decompress and requested_suffix is not None
        else requested
    )

    if remote_suffix and requested_suffix != remote_suffix:
        archive_path = Path(str(final_target) + remote_suffix)
    else:
        archive_path = requested

    if not overwrite:
        found = existing_variant(final_target)
        if found is not None:
            LOGGER.info("Using existing nonempty file %s", found)
            if decompress and compression_suffix(found) is not None:
                return decompress_file(found, final_target, overwrite=False)
            return found

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(archive_path.name + ".part")
    LOGGER.info("Downloading %s", url)
    try:
        with urlopen(url, timeout=timeout) as response:
            _copy_stream(response, archive_path)
    finally:
        temporary.unlink(missing_ok=True)

    remote_name = Path(urlparse(url).path).name
    if remote_name != archive_path.name:
        LOGGER.info("Renamed downloaded product %s -> %s", remote_name, archive_path)

    if decompress and compression_suffix(archive_path) is not None:
        return decompress_file(archive_path, final_target, overwrite=True)
    return archive_path


def download_first_available(
    urls: list[str] | tuple[str, ...],
    target: str | Path,
    *,
    overwrite: bool = False,
    decompress: bool = False,
    timeout: float = 60.0,
) -> Path:
    """Try alternate archive URLs in order and return the first success."""
    errors: list[str] = []
    for url in urls:
        try:
            return download_to_path(
                url,
                target,
                overwrite=overwrite,
                decompress=decompress,
                timeout=timeout,
            )
        except Exception as exc:  # archive alternatives can legitimately be absent
            errors.append(f"{url}: {exc}")
    raise OSError("no candidate URL was available; " + "; ".join(errors))
