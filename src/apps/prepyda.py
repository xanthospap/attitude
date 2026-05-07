#!/usr/bin/env python3

"""
Download/preprocess the external products referenced by a DORIS processing YAML file.

The script intentionally reuses the same project functions as the existing single-purpose
scripts instead of shelling out to them:

  * RINEX       -> sources.ign.download_rinex
  * VMF3 grids  -> sources.vmf.download_vmf
  * Attitude    -> sources.cddis/copernicus download + preprocessors.attitude.preprocess_attitude
  * SP3 orbits  -> sources.ign/download_orbits or sources.cddis.download_orbits
  * Sat mass    -> sources.ids.download_satmass, if requested or present in YAML

Example:

    python prep_products.py s6a_test.yaml --uncompress --overwrite

Paths found in the YAML are resolved relative to the YAML file location.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import-time environment issue
    raise SystemExit("ERROR: PyYAML is required. Install with: pip install pyyaml") from exc


LOGGER = logging.getLogger("prep_products")

DEFAULT_PRODUCTS = ("rinex", "vmf3", "satmass", "attitude", "sp3")
SATELLITE_PRODUCTS = {"rinex", "satmass", "attitude", "sp3"}


def parse_datetime(value: Any) -> dt.datetime:
    """Parse YAML/CLI date values into naive datetimes."""
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=None)

    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())

    if value is None:
        raise ValueError("missing datetime value")

    text = str(value).strip().replace("Z", "")
    parsed = dt.datetime.fromisoformat(text)
    return parsed.replace(tzinfo=None)


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def resolve_path(value: Any, root: Path) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def first_path(root: Path, *values: Any, default: str | Path = "data") -> Path:
    for value in values:
        path = resolve_path(value, root)
        if path is not None:
            return path
    default_path = Path(default)
    if not default_path.is_absolute():
        default_path = root / default_path
    return default_path


def mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a YAML mapping at the top level")
    return data


def get_date_range(config: dict[str, Any], begin: str | None, end: str | None) -> tuple[dt.datetime, dt.datetime]:
    rinex_cfg = config.get("rinex") or {}
    start_value = begin if begin is not None else rinex_cfg.get("from")
    end_value = end if end is not None else rinex_cfg.get("to")

    start = parse_datetime(start_value)
    stop = parse_datetime(end_value)
    if stop <= start:
        raise ValueError(f"end date must be after start date: {start!s} -> {stop!s}")
    return start, stop


def get_satellites(config: dict[str, Any], cli_satellites: list[str] | None) -> list[str]:
    if cli_satellites:
        satellites = cli_satellites
    else:
        sat_cfg = config.get("satellite-attitude") or {}
        satellites = (
            ensure_list(config.get("satellites"))
            or ensure_list(sat_cfg.get("satellites"))
            or ensure_list(sat_cfg.get("satellite"))
        )

    satellites = [sat.strip().lower() for sat in satellites if sat and sat.strip()]
    return list(dict.fromkeys(satellites))


def get_products(raw_products: list[str]) -> list[str]:
    requested = [item.lower() for item in raw_products]
    if "all" in requested:
        return list(DEFAULT_PRODUCTS)
    return [product for product in DEFAULT_PRODUCTS if product in requested]


def append_result(results: dict[str, list[str]], product: str, files: Iterable[Path | str]) -> None:
    results.setdefault(product, [])
    for file in files:
        results[product].append(str(file))


def download_rinex_product(
    satellite: str,
    start: dt.datetime,
    stop: dt.datetime,
    output_dir: Path,
    *,
    overwrite: bool,
    uncompress: bool,
) -> list[Path]:
    from sources import ign

    files = ign.download_rinex(
        satellite=satellite,
        start=start,
        end=stop,
        output_dir=output_dir,
        overwrite=overwrite,
        uncompress=uncompress,
    )
    if not files:
        raise RuntimeError(f"no RINEX files were downloaded for {satellite}")
    return [Path(file) for file in files]


def download_vmf3_product(
    start: dt.datetime,
    stop: dt.datetime,
    output_dir: Path,
    *,
    product_type: str,
    grid: str,
    overwrite: bool,
) -> list[Path]:
    from sources.vmf import download_vmf

    files = download_vmf(
        start=start,
        end=stop,
        output_dir=output_dir,
        product_type=product_type,
        grid=grid,
        overwrite=overwrite,
    )
    if not files:
        raise RuntimeError("no VMF3 grid files were downloaded")
    return [Path(file) for file in files]


def download_satmass_product(satellite: str, output_dir: Path, *, overwrite: bool) -> Path:
    from sources.ids import download_satmass

    file = download_satmass(
        satellite=satellite,
        output_dir=output_dir,
        overwrite=overwrite,
    )
    if not file:
        raise RuntimeError(f"no satellite mass file was downloaded for {satellite}")
    return Path(file)


def download_sp3_product(
    satellite: str,
    start: dt.datetime,
    stop: dt.datetime,
    output_dir: Path,
    *,
    source: str,
    center: str,
    version: str | None,
    overwrite: bool,
    uncompress: bool,
    ftp_user: str,
    ftp_password: str,
) -> list[Path]:
    source = source.lower()

    if source == "ign":
        from sources import ign

        files = ign.download_orbits(
            satellite=satellite,
            start=start,
            end=stop,
            output_dir=output_dir,
            center=center,
            version=version,
            overwrite=overwrite,
            uncompress=uncompress,
            user=ftp_user,
            password=ftp_password,
        )
    elif source == "cddis":
        from sources import cddis

        if uncompress:
            LOGGER.warning("SP3 --uncompress is implemented only for IGN downloads; CDDIS files stay compressed")
        files = cddis.download_orbits(
            satellite=satellite,
            start=start,
            end=stop,
            output_dir=output_dir,
            center=center,
            version=version,
            overwrite=overwrite,
        )
    else:
        raise ValueError(f"unsupported SP3 source {source!r}; use 'ign' or 'cddis'")

    if not files:
        raise RuntimeError(f"no SP3 files were downloaded for {satellite}")
    return [Path(file) for file in files]


def download_attitude_files(
    satellite: str,
    start: dt.datetime,
    stop: dt.datetime,
    output_dir: Path,
    *,
    overwrite: bool,
    s3cfg: Path | None,
) -> list[Path]:
    from sources import cddis, copernicus
    from sources.attitude import SATELLITE_INFO

    sat = satellite.lower()
    if sat not in SATELLITE_INFO:
        raise ValueError(f"unsupported attitude satellite {sat!r}; supported: {', '.join(sorted(SATELLITE_INFO))}")

    info = SATELLITE_INFO[sat]
    source = info["source"]

    if source == "cddis":
        files = cddis.download_attitude(
            satellite=sat,
            start=start,
            end=stop,
            output_dir=output_dir,
            base_url=info["base_url"],
            data_types=info["data_types"],
            overwrite=overwrite,
        )
    elif source == "copernicus":
        files = copernicus.download_attitude(
            satellite=sat,
            start=start,
            end=stop,
            output_dir=output_dir,
            base_url=info["base_url"],
            overwrite=overwrite,
            s3cfg=s3cfg,
        )
    elif source == "ign":
        raise NotImplementedError("SWOT/IGN attitude source adapter is not migrated yet")
    else:
        raise ValueError(f"unsupported attitude source {source!r}")

    if not files:
        raise RuntimeError(f"no attitude files were downloaded for {sat}")
    return [Path(file) for file in files]


def keep_overlapping_attitude_files(files: Iterable[Path], start: dt.datetime, stop: dt.datetime) -> list[Path]:
    """Keep only attitude files whose product-name time span overlaps the requested range."""
    from sources.attitude import product_overlaps_range

    selected = [Path(file) for file in files if product_overlaps_range(Path(file).name, start, stop)]
    if not selected:
        LOGGER.warning("no downloaded attitude products overlap %s to %s; using all downloaded files", start, stop)
        return [Path(file) for file in files]
    return selected


def preprocess_attitude_product(
    satellite: str,
    raw_files: Iterable[Path],
    start: dt.datetime,
    stop: dt.datetime,
    *,
    nsec: float,
    output_file: Path,
) -> Path:
    from preprocessors.attitude import preprocess_attitude

    file = preprocess_attitude(
        satellite=satellite,
        qfns=list(raw_files),
        nsec=nsec,
        start=start,
        end=stop,
        output_file=output_file,
    )
    return Path(file)


def planned_summary(
    *,
    config_path: Path,
    products: list[str],
    satellites: list[str],
    start: dt.datetime,
    stop: dt.datetime,
    directories: dict[str, Path],
) -> dict[str, Any]:
    return {
        "config": str(config_path),
        "start": start.isoformat(sep=" "),
        "end": stop.isoformat(sep=" "),
        "satellites": satellites,
        "products": products,
        "directories": {key: str(value) for key, value in directories.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prep_products",
        description="Read a processing YAML and download/preprocess required RINEX, VMF3, attitude, SP3, and satellite-mass products.",
    )
    parser.add_argument("config", type=Path, help="Processing YAML file, e.g. s6a_test.yaml")
    parser.add_argument("--begin", help="Override YAML rinex.from date/datetime")
    parser.add_argument("--end", help="Override YAML rinex.to date/datetime")
    parser.add_argument("-s", "--satellite", action="append", help="Satellite ID. Repeat for multiple satellites. Defaults to YAML satellite-attitude.satellite.")
    parser.add_argument(
        "--products",
        nargs="+",
        default=["all"],
        choices=["all", *DEFAULT_PRODUCTS],
        help="Products to prepare. Default: all.",
    )
    parser.add_argument("--data-dir", type=Path, help="Override all product output directories")
    parser.add_argument("--overwrite", action="store_true", help="Redownload products even if they exist")
    parser.add_argument("--uncompress", action="store_true", help="Uncompress RINEX and IGN SP3 .Z files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without downloading")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue with later products/satellites after an error")
    parser.add_argument("--manifest", type=Path, help="Optional JSON file where downloaded/prepared paths are written")

    parser.add_argument("--vmf-type", default=None, help="VMF product type. Default: YAML troposphere.type or v3gr")
    parser.add_argument("--vmf-grid", default=None, choices=["1x1", "5x5"], help="VMF grid resolution. Default: YAML troposphere.grid or 5x5")

    parser.add_argument("--sp3-source", choices=["ign", "cddis"], default=None, help="SP3 archive source. Default: YAML sp3.source/orbits.source or ign")
    parser.add_argument("--sp3-center", default=None, help="SP3 analysis center. Default: YAML sp3.center/orbits.center or ssa")
    parser.add_argument("--sp3-version", default=None, help="Optional SP3 product version filter")
    parser.add_argument("--ftp-user", default="anonymous", help="FTP username for IGN SP3. Default: anonymous")
    parser.add_argument("--ftp-password", default="anonymous@", help="FTP password for IGN SP3. Default: anonymous@")

    parser.add_argument("--attitude-every-sec", type=float, default=None, help="Attitude interpolation interval. Default: YAML satellite-attitude.every_sec/nsec or 5")
    parser.add_argument("--s3cfg", type=Path, default=None, help="Copernicus S3 config for attitude products")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        style="{",
        format="{levelname}: {name} ({funcName}) [{lineno}]: {message}",
    )

    config_path = args.config.expanduser().resolve()
    config = load_config(config_path)
    root = config_path.parent

    products = get_products(args.products)
    start, stop = get_date_range(config, args.begin, args.end)
    satellites = get_satellites(config, args.satellite)

    if any(product in SATELLITE_PRODUCTS for product in products) and not satellites:
        raise SystemExit("ERROR: no satellite was provided. Use --satellite or YAML satellite-attitude.satellite.")

    rinex_cfg = config.get("rinex") or {}
    trop_cfg = config.get("troposphere") or {}
    attitude_cfg = config.get("satellite-attitude") or {}
    sp3_cfg = config.get("sp3") or config.get("orbits") or {}

    data_dir_override = resolve_path(args.data_dir, root) if args.data_dir else None
    default_data_dir = first_path(root, rinex_cfg.get("data_dir"), trop_cfg.get("data_dir"), default="data")

    rinex_dir = mkdir(data_dir_override or first_path(root, rinex_cfg.get("data_dir"), default=default_data_dir))
    vmf_dir = mkdir(data_dir_override or first_path(root, trop_cfg.get("data_dir"), default=default_data_dir))
    sp3_dir = mkdir(data_dir_override or first_path(root, sp3_cfg.get("data_dir"), default=default_data_dir))

    configured_attitude_output = resolve_path(attitude_cfg.get("data_file"), root)
    attitude_dir = mkdir(
        data_dir_override
        or first_path(
            root,
            attitude_cfg.get("data_dir"),
            configured_attitude_output.parent if configured_attitude_output else None,
            default=default_data_dir,
        )
    )

    configured_mass_file = resolve_path(attitude_cfg.get("cnes_sat_file"), root)
    satmass_dir = mkdir(
        data_dir_override
        or first_path(
            root,
            attitude_cfg.get("mass_data_dir"),
            configured_mass_file.parent if configured_mass_file else None,
            default=default_data_dir,
        )
    )

    directories = {
        "rinex": rinex_dir,
        "vmf3": vmf_dir,
        "satmass": satmass_dir,
        "attitude": attitude_dir,
        "sp3": sp3_dir,
    }

    plan = planned_summary(
        config_path=config_path,
        products=products,
        satellites=satellites,
        start=start,
        stop=stop,
        directories=directories,
    )

    LOGGER.info("Plan:\n%s", json.dumps(plan, indent=2))
    if args.dry_run:
        print(json.dumps({"dry_run": True, **plan}, indent=2))
        return 0

    results: dict[str, list[str]] = {}
    errors: list[str] = []

    def run_step(label: str, func) -> None:
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - CLI should summarize product failures
            message = f"{label}: {exc}"
            errors.append(message)
            if args.continue_on_error:
                LOGGER.exception("FAILED: %s", label)
            else:
                raise

    if "vmf3" in products:
        model = str(trop_cfg.get("model") or "").upper()
        if model and model != "VMF3":
            LOGGER.info("Skipping VMF3 download because troposphere.model is %r", trop_cfg.get("model"))
        else:
            vmf_type = args.vmf_type or trop_cfg.get("type") or trop_cfg.get("product_type") or "v3gr"
            vmf_grid = args.vmf_grid or trop_cfg.get("grid") or "5x5"

            def _vmf3() -> None:
                files = download_vmf3_product(
                    start,
                    stop,
                    vmf_dir,
                    product_type=str(vmf_type),
                    grid=str(vmf_grid),
                    overwrite=args.overwrite,
                )
                append_result(results, "vmf3", files)
                LOGGER.info("VMF3: %d file(s)", len(files))

            run_step("VMF3", _vmf3)

    for satellite in satellites:
        if "rinex" in products:
            def _rinex(sat: str = satellite) -> None:
                files = download_rinex_product(
                    sat,
                    start,
                    stop,
                    rinex_dir,
                    overwrite=args.overwrite,
                    uncompress=args.uncompress,
                )
                append_result(results, f"rinex:{sat}", files)
                LOGGER.info("RINEX %s: %d file(s)", sat, len(files))

            run_step(f"RINEX {satellite}", _rinex)

        if "satmass" in products:
            def _satmass(sat: str = satellite) -> None:
                file = download_satmass_product(sat, satmass_dir, overwrite=args.overwrite)
                append_result(results, f"satmass:{sat}", [file])
                LOGGER.info("Satellite mass %s: %s", sat, file)
                if configured_mass_file and len(satellites) == 1 and Path(file).resolve() != configured_mass_file.resolve():
                    LOGGER.warning(
                        "YAML cnes_sat_file is %s, but downloader returned %s. Update the YAML if needed.",
                        configured_mass_file,
                        file,
                    )

            run_step(f"satmass {satellite}", _satmass)

        if "attitude" in products:
            def _attitude(sat: str = satellite) -> None:
                raw_files = download_attitude_files(
                    sat,
                    start,
                    stop,
                    attitude_dir,
                    overwrite=args.overwrite,
                    s3cfg=args.s3cfg,
                )
                raw_files = keep_overlapping_attitude_files(raw_files, start, stop)

                if configured_attitude_output and len(satellites) == 1:
                    attitude_output = configured_attitude_output
                else:
                    attitude_output = attitude_dir / f"qua_{sat}.csv"
                attitude_output.parent.mkdir(parents=True, exist_ok=True)

                prepared_file = preprocess_attitude_product(
                    sat,
                    raw_files,
                    start,
                    stop,
                    nsec=args.attitude_every_sec or attitude_cfg.get("every_sec") or attitude_cfg.get("nsec") or 5.0,
                    output_file=attitude_output,
                )
                append_result(results, f"attitude_raw:{sat}", raw_files)
                append_result(results, f"attitude_prepared:{sat}", [prepared_file])
                LOGGER.info("Attitude %s: %s", sat, prepared_file)

            run_step(f"attitude {satellite}", _attitude)

        if "sp3" in products:
            sp3_source = args.sp3_source or sp3_cfg.get("source") or "ign"
            sp3_center = args.sp3_center or sp3_cfg.get("center") or "ssa"
            sp3_version = args.sp3_version if args.sp3_version is not None else sp3_cfg.get("version")
            sp3_uncompress = args.uncompress or as_bool(sp3_cfg.get("uncompress"), default=False)

            def _sp3(sat: str = satellite) -> None:
                files = download_sp3_product(
                    sat,
                    start,
                    stop,
                    sp3_dir,
                    source=str(sp3_source),
                    center=str(sp3_center),
                    version=None if sp3_version in (None, "") else str(sp3_version),
                    overwrite=args.overwrite,
                    uncompress=sp3_uncompress,
                    ftp_user=args.ftp_user,
                    ftp_password=args.ftp_password,
                )
                append_result(results, f"sp3:{sat}", files)
                LOGGER.info("SP3 %s: %d file(s)", sat, len(files))

            run_step(f"SP3 {satellite}", _sp3)

    output = {"plan": plan, "results": results, "errors": errors}
    if args.manifest:
        manifest_path = resolve_path(args.manifest, Path.cwd()) or args.manifest
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        LOGGER.info("Wrote manifest %s", manifest_path)

    print(json.dumps(output, indent=2))

    if errors:
        for error in errors:
            LOGGER.error(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
