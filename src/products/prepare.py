from __future__ import annotations

import csv
import datetime as dt
import logging
from pathlib import Path
import re
from typing import Callable

from products.config import PreparationContext, mapping_if_present, resolve_path
from products.result import ProductResult
from sources.files import (
    download_first_available,
    download_to_path,
    is_nonempty_file,
    uncompressed_path,
)
from sources.rinex import dates_touched_by_range, ign_rinex_url, rinex_filename
from sources.vmf import vmf_epochs_for_range, vmf_url


LOGGER = logging.getLogger(__name__)

EOP_URL = "https://hpiers.obspm.fr/iers/eop/eopc04_20_v3/eopc04.1962-now"
SPACE_WEATHER_URL = "https://celestrak.org/SpaceData/SW-Last5Years.csv"
IDS_SATELLITE_HTTPS = "https://ids-doris.org/documents/BC/satellites"
IGN_DPOD_BASE = "ftp://doris.ign.fr/pub/doris/products/dpod"
AOD1B_BASE = "https://isdc-data.gfz.de/grace/Level-1B/GFZ/AOD"
ATTITUDE_MARGIN = dt.timedelta(minutes=30)
VMF_OROGRAPHY_URLS = {
    "5x5": "https://vmf.geo.tuwien.ac.at/station_coord_files/orography_ell_5x5",
    "1x1": "https://vmf.geo.tuwien.ac.at/station_coord_files/orography_ell_1x1",
}


def _warning(result: ProductResult, item: str, exc: Exception | str) -> None:
    message = f"{result.product}: unavailable {item}: {exc}"
    result.add_missing(item, message)


def _download(
    result: ProductResult,
    url: str,
    target: Path,
    context: PreparationContext,
) -> None:
    try:
        result.add_available(
            download_to_path(
                url,
                target,
                overwrite=context.overwrite,
                decompress=context.decompress,
            )
        )
    except Exception as exc:
        _warning(result, str(target), exc)


def prepare_rinex(context: PreparationContext) -> ProductResult:
    result = ProductResult("rinex")
    node = mapping_if_present(context.config, "rinex")
    if node is None or node.get("data_dir") in (None, ""):
        return result
    output_dir = resolve_path(node["data_dir"], context.root)
    assert output_dir is not None

    for entry in context.satellites:
        satellite = entry["satellite"]
        for day in dates_touched_by_range(context.start, context.stop):
            filename = rinex_filename(satellite, day)
            target = output_dir / (filename[:-2] if context.decompress else filename)
            _download(result, ign_rinex_url(satellite, day), target, context)
    return result


def prepare_vmf3(context: PreparationContext) -> ProductResult:
    result = ProductResult("vmf3")
    node = mapping_if_present(context.config, "troposphere")
    if node is None or str(node.get("model", "")).upper() != "VMF3":
        return result
    data_dir = resolve_path(node.get("data_dir"), context.root)
    if data_dir is None:
        return result
    grid = str(node.get("grid", "5x5"))
    product_type = str(node.get("type", node.get("product_type", "v3gr")))

    # vmf_epochs_for_range supplies both bracketing epochs: floor(start) and
    # ceil(stop).  No second, hidden margin is added here.
    for epoch in vmf_epochs_for_range(context.start, context.stop):
        url = vmf_url(epoch, product_type=product_type, grid=grid)
        _download(result, url, data_dir / Path(url).name, context)

    try:
        url = VMF_OROGRAPHY_URLS[grid]
    except KeyError as exc:
        raise ValueError(f"unknown VMF3 grid {grid!r}") from exc
    _download(result, url, data_dir / Path(url).name, context)
    return result


def _dpod_urls(target: Path) -> list[str]:
    remote_name = uncompressed_path(target).name
    match = re.search(r"dpod(?P<frame>\d{4})", remote_name, re.IGNORECASE)
    if match is None:
        raise ValueError(
            f"cannot infer DPOD archive directory from filename {target.name!r}"
        )
    base = f"{IGN_DPOD_BASE}/dpod{match.group('frame')}"
    return [f"{base}/{remote_name}.Z", f"{base}/{remote_name}.gz", f"{base}/{remote_name}"]


def prepare_dpod(context: PreparationContext) -> ProductResult:
    result = ProductResult("dpod")
    node = mapping_if_present(context.config, "a-priori-coordinates")
    if node is None:
        return result
    for key in ("sinex", "dpod_frequency_cor"):
        target = resolve_path(node.get(key), context.root)
        if target is None:
            continue
        try:
            result.add_available(
                download_first_available(
                    _dpod_urls(target),
                    target,
                    overwrite=context.overwrite,
                    decompress=context.decompress,
                )
            )
        except Exception as exc:
            _warning(result, str(target), exc)
    return result


def _coverage_from_eop(path: Path) -> tuple[dt.datetime, dt.datetime] | None:
    first = last = None
    try:
        with path.open("r", encoding="ascii", errors="ignore") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) < 3:
                    continue
                try:
                    value = dt.datetime(int(fields[0]), int(fields[1]), int(fields[2]))
                except (ValueError, IndexError):
                    continue
                first = value if first is None else min(first, value)
                last = value if last is None else max(last, value)
    except OSError:
        return None
    return None if first is None or last is None else (first, last + dt.timedelta(days=1))


def _coverage_from_space_weather(path: Path) -> tuple[dt.datetime, dt.datetime] | None:
    dates: list[dt.datetime] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as stream:
            reader = csv.DictReader(stream)
            for row in reader:
                raw = row.get("DATE") or row.get("Date") or row.get("date")
                if not raw:
                    continue
                try:
                    dates.append(dt.datetime.fromisoformat(raw.strip()).replace(tzinfo=None))
                except ValueError:
                    continue
    except OSError:
        return None
    return None if not dates else (min(dates), max(dates) + dt.timedelta(days=1))


def _covers(
    path: Path,
    start: dt.datetime,
    stop: dt.datetime,
    scanner: Callable[[Path], tuple[dt.datetime, dt.datetime] | None],
) -> bool:
    if not is_nonempty_file(path):
        return False
    coverage = scanner(path)
    return coverage is not None and coverage[0] <= start and coverage[1] >= stop


def _prepare_continuously_updated(
    context: PreparationContext,
    product: str,
    url: str,
    target: Path | None,
    scanner: Callable[[Path], tuple[dt.datetime, dt.datetime] | None],
) -> ProductResult:
    result = ProductResult(product)
    if target is None:
        return result
    overwrite = context.overwrite
    if is_nonempty_file(target) and not overwrite:
        if _covers(target, context.start, context.stop, scanner):
            result.add_available(target)
            return result
        LOGGER.info(
            "Existing %s does not cover %s -> %s; refreshing it",
            target,
            context.start,
            context.stop,
        )
        overwrite = True
    try:
        downloaded = download_to_path(
            url,
            target,
            overwrite=overwrite,
            decompress=context.decompress,
        )
        result.add_available(downloaded)
        if not _covers(downloaded, context.start, context.stop, scanner):
            message = f"{product}: {downloaded} does not cover the requested UTC interval"
            LOGGER.warning(message)
            result.warnings.append(message)
    except Exception as exc:
        _warning(result, str(target), exc)
    return result


def prepare_eop(context: PreparationContext) -> ProductResult:
    return _prepare_continuously_updated(
        context,
        "eop",
        EOP_URL,
        resolve_path(context.config.get("eop"), context.root),
        _coverage_from_eop,
    )


def prepare_space_weather(context: PreparationContext) -> ProductResult:
    node = mapping_if_present(context.config, "space-weather-data")
    target = None if node is None else resolve_path(node.get("celestrak_csv"), context.root)
    return _prepare_continuously_updated(
        context,
        "space-weather",
        SPACE_WEATHER_URL,
        target,
        _coverage_from_space_weather,
    )


def prepare_satellite_files(context: PreparationContext) -> ProductResult:
    result = ProductResult("satellite-files")
    for entry in context.satellites:
        satellite = entry["satellite"]
        for key, suffix in (("cnes_sat_file", "mass.txt"), ("cnes_maneuver", "man.txt")):
            target = resolve_path(entry.get(key), context.root)
            if target is None:
                continue
            url = f"{IDS_SATELLITE_HTTPS}/{satellite}{suffix}"
            _download(result, url, target, context)
    return result


def _attitude_coverage(path: Path) -> tuple[dt.datetime, dt.datetime] | None:
    """Read only the first two numeric columns of a prepared attitude file."""
    from astropy.time import Time

    epochs: list[float] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) < 2:
                    continue
                try:
                    mjd = float(fields[0]) + float(fields[1]) / 86400.0
                except ValueError:
                    continue
                if 30000.0 < mjd < 100000.0:
                    epochs.append(mjd)
    except OSError:
        return None
    if not epochs:
        return None
    first = Time(min(epochs), format="mjd", scale="tt").utc.datetime.replace(tzinfo=None)
    last = Time(max(epochs), format="mjd", scale="tt").utc.datetime.replace(tzinfo=None)
    return first, last


def prepare_attitude(context: PreparationContext) -> ProductResult:
    """Prepare configured attitude outputs, refreshing insufficient files."""
    from apps.attitude import download_attitude_files
    from preprocessors.attitude import preprocess_attitude
    from sources.attitude import SATELLITE_INFO, product_overlaps_range

    result = ProductResult("attitude")
    requested_start = context.start - ATTITUDE_MARGIN
    requested_stop = context.stop + ATTITUDE_MARGIN

    for entry in context.satellites:
        target = resolve_path(entry.get("data_file"), context.root)
        if target is None:
            continue
        satellite = entry["satellite"]
        if satellite not in SATELLITE_INFO:
            raise ValueError(f"no attitude source is registered for satellite {satellite!r}")

        coverage = _attitude_coverage(target) if is_nonempty_file(target) else None
        if (
            not context.overwrite
            and coverage is not None
            and coverage[0] <= requested_start
            and coverage[1] >= requested_stop
        ):
            LOGGER.info("Using attitude file %s; it covers the requested interval", target)
            result.add_available(target)
            continue

        if is_nonempty_file(target):
            LOGGER.info(
                "Attitude file %s does not cover the requested interval; refreshing it",
                target,
            )

        raw_dir = target.parent / "attitude_raw" / satellite
        try:
            raw_files = download_attitude_files(
                satellite=satellite,
                start=requested_start,
                end=requested_stop,
                save_dir=raw_dir,
                overwrite=context.overwrite,
                s3cfg=context.attitude_s3cfg,
                user=context.attitude_user,
                password=context.attitude_password,
            )
        except Exception as exc:
            _warning(result, str(target), exc)
            continue

        overlapping = [
            Path(path)
            for path in raw_files
            if product_overlaps_range(Path(path).name, requested_start, requested_stop)
        ]
        if not overlapping:
            _warning(
                result,
                str(target),
                "no downloaded attitude product overlaps the requested interval",
            )
            continue

        try:
            nsec = float(entry.get("every_sec", entry.get("nsec", 5.0)))
            prepared = preprocess_attitude(
                satellite=satellite,
                qfns=overlapping,
                nsec=nsec,
                start=requested_start,
                end=requested_stop,
                output_file=target,
            )
            result.add_available(prepared)
            coverage = _attitude_coverage(Path(prepared))
            if (
                coverage is None
                or coverage[0] > requested_start
                or coverage[1] < requested_stop
            ):
                message = (
                    f"attitude: {prepared} does not fully cover the requested "
                    "interpolation interval"
                )
                LOGGER.warning(message)
                result.warnings.append(message)
        except Exception as exc:
            _warning(result, str(target), exc)
    return result


def _aod_release(model: object) -> str | None:
    match = re.search(r"RL\s*0?([67])", str(model), re.IGNORECASE)
    return None if match is None else f"RL0{match.group(1)}"


def prepare_aod1b(context: PreparationContext) -> ProductResult:
    result = ProductResult("aod1b")
    node = mapping_if_present(context.config, "dealiasing")
    if node is None or str(node.get("model", "")).lower() in {"", "null", "none"}:
        return result
    release = _aod_release(node.get("model"))
    if release is None:
        raise ValueError(f"unknown dealiasing model {node.get('model')!r}")
    data_dir = resolve_path(node.get("data-dir", node.get("data_dir")), context.root)
    if data_dir is None:
        return result

    # AOD1B records occur every three hours.  Include one record before and
    # after the processing interval so interpolation is bracketed at both ends.
    start = context.start - dt.timedelta(hours=3)
    stop = context.stop + dt.timedelta(hours=3)
    release_number = release[-2:]
    for day in dates_touched_by_range(start, stop):
        filename = f"AOD1B_{day:%Y-%m-%d}_X_{release_number}.asc.gz"
        url = f"{AOD1B_BASE}/{release}/{day.year:04d}/{filename}"
        target_name = filename[:-3] if context.decompress else filename
        _download(result, url, data_dir / target_name, context)
    return result


def prepare_atmospheric_tides(context: PreparationContext) -> ProductResult:
    result = ProductResult("atmospheric-tides")
    node = mapping_if_present(context.config, "atmospheric-tide")
    if node is None or str(node.get("model", "")).lower() in {"", "null", "none"}:
        return result
    release = _aod_release(node.get("model"))
    if release is None:
        return result  # GROOPS atlas: its file list is user-managed, not downloaded here.
    if release != "RL06":
        raise ValueError("AOD1B atmospheric-tide downloading is supported only for RL06")
    data_dir = resolve_path(node.get("data_dir", node.get("data-dir")), context.root)
    files = node.get("tide_atlas_from_aod1b")
    if data_dir is None or files is None:
        return result
    if not isinstance(files, dict):
        raise ValueError("atmospheric-tide.tide_atlas_from_aod1b must be a mapping")
    for constituent, filename_value in files.items():
        if filename_value in (None, ""):
            continue
        target = data_dir / str(filename_value)
        remote_name = uncompressed_path(target).name
        url = f"{AOD1B_BASE}/RL06/TIDES/{remote_name}.gz"
        try:
            result.add_available(
                download_to_path(
                    url,
                    target,
                    overwrite=context.overwrite,
                    decompress=context.decompress,
                )
            )
        except Exception as exc:
            _warning(result, f"{constituent}:{target}", exc)
    return result


PRODUCT_HANDLERS: dict[str, Callable[[PreparationContext], ProductResult]] = {
    "rinex": prepare_rinex,
    "dpod": prepare_dpod,
    "vmf3": prepare_vmf3,
    "eop": prepare_eop,
    "aod1b": prepare_aod1b,
    "atmospheric-tides": prepare_atmospheric_tides,
    "space-weather": prepare_space_weather,
    "satellite-files": prepare_satellite_files,
    "attitude": prepare_attitude,
}
