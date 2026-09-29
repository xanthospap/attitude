#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from products.config import load_config, make_context
from products.prepare import PRODUCT_HANDLERS


LOGGER = logging.getLogger("prepyda")
DEFAULT_PRODUCTS = tuple(PRODUCT_HANDLERS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepyda",
        description=(
            "Read a dpod YAML file and prepare every configured external product. "
            "Relative YAML paths are resolved below --root-dir."
        ),
    )
    parser.add_argument("config", type=Path, help="dpod YAML configuration")
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path.cwd(),
        help="Root for relative YAML paths. Default: current working directory.",
    )
    parser.add_argument(
        "--products",
        nargs="+",
        choices=["all", *DEFAULT_PRODUCTS],
        default=["all"],
        help="Product handlers to run. Default: all configured products.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Refresh products even when a nonempty local variant exists.",
    )
    parser.add_argument(
        "--decompress",
        dest="decompress",
        action="store_true",
        default=True,
        help="Decompress downloaded or existing compressed products (default).",
    )
    parser.add_argument(
        "--no-decompress",
        dest="decompress",
        action="store_false",
        help="Keep compressed product files.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("downloads.json"),
        help="JSON summary path, relative to --root-dir by default.",
    )
    parser.add_argument("--s3cfg", type=Path, help="Copernicus S3 configuration")
    parser.add_argument("--attitude-ftp-user", help="CryoSat FTPS username")
    parser.add_argument("--attitude-ftp-password", help="CryoSat FTPS password")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        style="{",
        format="{levelname}: {name}: {message}",
    )

    config_path = args.config.expanduser().resolve()
    root = args.root_dir.expanduser().resolve()
    config = load_config(config_path)
    context = make_context(
        config,
        root,
        overwrite=args.overwrite,
        decompress=args.decompress,
        attitude_s3cfg=args.s3cfg,
        attitude_user=args.attitude_ftp_user,
        attitude_password=args.attitude_ftp_password,
    )

    names = list(DEFAULT_PRODUCTS) if "all" in args.products else args.products
    results = []
    for name in names:
        LOGGER.info("Preparing %s", name)
        result = PRODUCT_HANDLERS[name](context)
        results.append(result)
        for warning in result.warnings:
            LOGGER.warning("%s", warning)

    manifest = args.manifest.expanduser()
    if not manifest.is_absolute():
        manifest = root / manifest
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": str(config_path),
        "root_dir": str(root),
        "interval_utc": {
            "start": context.start.isoformat(sep=" "),
            "stop": context.stop.isoformat(sep=" "),
        },
        "products": [result.as_dict() for result in results],
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote manifest %s", manifest)

    missing = sum(len(result.missing) for result in results)
    if missing:
        LOGGER.warning("Preparation completed with %d unavailable product file(s)", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
