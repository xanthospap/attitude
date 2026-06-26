#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot parameter solutions from one or more SINEX_TRO files.

This command-line script is a small plotting front-end for ``tropo_sinex.py``.
It expects ``tropo_sinex.py`` to be importable, either because it is in the
same directory as this script, because it is in the current working directory,
or because its directory is listed in ``PYTHONPATH``.

Examples
--------
Plot ZTD/TROTOT for one station from one file and show the figure interactively::

    python plot_tropo_sinex.py \
        -b 2013:168:00000 \
        -e 2013:169:00000 \
        -s GOPE00CZE \
        -p TROTOT \
        GOP2OPSFIN_20131680000_01D_05M_TRO.TRO

Overlay the same station/parameter from several SINEX_TRO files::

    python plot_tropo_sinex.py \
        -b 2020-01-01 \
        -e 2020-01-04 \
        -s DYNG00GRC \
        -p TROWET \
        -o dyng_trowet.png \
        data/dyngtrop/DYNG.2020.001.trop \
        data/dyngtrop/DYNG.2020.002.trop \
        data/dyngtrop/DYNG.2020.003.trop

Date inputs are passed through to ``TropoSinex.get(...)`` and may therefore be
ISO-8601 strings such as ``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM:SS``, or SINEX_TRO
epoch strings such as ``YYYY:DOY:SOD``.  If ``--begin`` and/or ``--end`` are
omitted, the script uses ``datetime.datetime.min`` and/or
``datetime.datetime.max`` so that the full available data span is plotted.
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from parsers.tropo_sinex import TropoSinex


ScalarValue = Optional[float]
StddevValue = Dict[str, Optional[float]]
SeriesValue = Union[ScalarValue, StddevValue]
TimeSeries = Sequence[Tuple[object, SeriesValue]]
DateBound = Union[str, datetime.datetime]


PARAMETER_DESCRIPTIONS = {
    "TROTOT": "Zenith total tropospheric delay",
    "TROWET": "Zenith wet tropospheric delay",
    "TRODRY": "Zenith dry/hydrostatic tropospheric delay",
    "TGNTOT": "North total gradient",
    "TGNWET": "North wet gradient",
    "TGNDRY": "North dry gradient",
    "TGETOT": "East total gradient",
    "TGEWET": "East wet gradient",
    "TGEDRY": "East dry gradient",
    "STDDEV": "Standard deviation of estimated parameters",
    "IWV": "Integrated water vapour",
}


def build_arg_parser() -> argparse.ArgumentParser:
    """Create and return the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Plot a station parameter time series from one or more SINEX_TRO files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "tropo_sinex_files",
        metavar="TROPO_SINEX_FILE",
        nargs="+",
        help=(
            "Path(s) to SINEX_TRO files to read. Plain text and .gz files are "
            "supported by tropo_sinex.py. When more than one file is given, "
            "the time series are overlaid on the same plot."
        ),
    )
    parser.add_argument(
        "-b",
        "--begin",
        required=False,
        default=None,
        help=(
            "Inclusive start date/time. Examples: 2013:168:00000, "
            "2013-06-17, 2013-06-17T00:00:00. If omitted, "
            "datetime.datetime.min is used and all earlier available data are included."
        ),
    )
    parser.add_argument(
        "-e",
        "--end",
        required=False,
        default=None,
        help=(
            "Exclusive end date/time. Examples: 2013:169:00000, "
            "2013-06-18, 2013-06-18T00:00:00. If omitted, "
            "datetime.datetime.max is used and all later available data are included."
        ),
    )
    parser.add_argument(
        "-s",
        "--station",
        required=True,
        help="Station site code, normally the 9-character Site Code, e.g. GOPE00CZE.",
    )
    parser.add_argument(
        "-p",
        "--parameter",
        required=True,
        choices=sorted(PARAMETER_DESCRIPTIONS),
        type=str.upper,
        help="Tropospheric parameter type to plot.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output image filename. If omitted, the plot is shown interactively.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Output image DPI when --output is used.",
    )
    parser.add_argument(
        "--marker",
        default=".",
        help="Matplotlib marker style for plotted samples. Use an empty string for no marker.",
    )
    parser.add_argument(
        "--line-style",
        default="-",
        help="Matplotlib line style. Use an empty string to plot markers only.",
    )
    parser.add_argument(
        "--list-available",
        action="store_true",
        help="Print available sites and parameters from each file before plotting.",
    )
    return parser


def remove_missing_samples(
    epochs: Sequence[object], values: Sequence[Optional[float]]
) -> Tuple[List[object], List[float]]:
    """Return epochs and values after dropping missing ``None`` samples."""

    clean_epochs: List[object] = []
    clean_values: List[float] = []
    for epoch, value in zip(epochs, values):
        if value is not None:
            clean_epochs.append(epoch)
            clean_values.append(value)
    return clean_epochs, clean_values


def plot_scalar_series(
    ax: plt.Axes,
    series: TimeSeries,
    label: str,
    marker: str,
    line_style: str,
) -> int:
    """Plot an ordinary scalar parameter and return the number of plotted samples."""

    epochs = [epoch for epoch, _ in series]
    values = [value for _, value in series]
    clean_epochs, clean_values = remove_missing_samples(epochs, values)  # type: ignore[arg-type]
    if clean_values:
        ax.plot(clean_epochs, clean_values, linestyle=line_style, marker=marker, label=label)
    return len(clean_values)


def plot_stddev_series(
    ax: plt.Axes,
    series: TimeSeries,
    marker: str,
    line_style: str,
    label_prefix: str = "",
) -> int:
    """Plot the special ``STDDEV`` result returned by ``TropoSinex.get``.

    ``STDDEV`` is special because SINEX_TRO may include several STDDEV columns,
    each one associated with the parameter immediately before it.  The
    ``TropoSinex`` class returns each epoch as a dictionary such as::

        {"TROTOT": 0.0005, "TGNTOT": 0.0001, "TGETOT": 0.0001}

    This function plots one line per dictionary key.
    """

    owners: List[str] = sorted(
        {
            owner
            for _, value in series
            if isinstance(value, dict)
            for owner in value.keys()
        }
    )

    plotted = 0
    for owner in owners:
        epochs: List[object] = []
        values: List[Optional[float]] = []
        for epoch, value in series:
            if isinstance(value, dict):
                epochs.append(epoch)
                values.append(value.get(owner))
        clean_epochs, clean_values = remove_missing_samples(epochs, values)
        if clean_values:
            label = f"STDDEV({owner})"
            if label_prefix:
                label = f"{label_prefix}: {label}"
            ax.plot(clean_epochs, clean_values, linestyle=line_style, marker=marker, label=label)
            plotted += len(clean_values)
    return plotted


def source_labels(paths: Sequence[Path]) -> Dict[Path, str]:
    """Return readable and unique legend labels for input files.

    Basenames are easier to read in a plot legend.  If two input files have the
    same basename, fall back to each file's full path to avoid ambiguous labels.
    """

    basenames = [path.name for path in paths]
    if len(set(basenames)) == len(basenames):
        return {path: path.name for path in paths}
    return {path: str(path) for path in paths}


def format_time_axis(ax: plt.Axes) -> None:
    """Apply a readable date/time formatter to the x-axis."""

    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.figure.autofmt_xdate()


def make_plot(
    sinex_items: Sequence[Tuple[Path, TropoSinex]],
    station: str,
    parameter: str,
    begin: DateBound,
    end: DateBound,
    output: Optional[str],
    dpi: int,
    marker: str,
    line_style: str,
) -> None:
    """Fetch and plot a time series from one or more SINEX_TRO files.

    If several files are provided, their results are overlaid on the same axes.
    Files that do not contain the requested station/parameter/range are reported
    and skipped; the command fails only if no file contributes any sample.
    """

    if not sinex_items:
        raise SystemExit("At least one SINEX_TRO file is required.")

    paths = [path for path, _ in sinex_items]
    labels = source_labels(paths)
    multiple_files = len(sinex_items) > 1

    fig, ax = plt.subplots(figsize=(10, 5))
    ylabel = "STDDEV" if parameter == "STDDEV" else parameter
    total_plotted = 0
    skipped: List[str] = []

    for path, sinex in sinex_items:
        try:
            series = sinex.get(station, parameter, begin, end)
        except KeyError as exc:
            if multiple_files:
                skipped.append(f"{path}: {exc}")
                continue
            raise SystemExit(str(exc)) from exc

        if not series:
            skipped.append(
                f"{path}: no samples for station={station!r}, "
                f"parameter={parameter!r}, interval=[{begin}, {end})"
            )
            continue

        legend_label = labels[path] if multiple_files else parameter
        if parameter == "STDDEV":
            plotted_count = plot_stddev_series(
                ax,
                series,
                marker=marker,
                line_style=line_style,
                label_prefix=labels[path] if multiple_files else "",
            )
        else:
            plotted_count = plot_scalar_series(
                ax,
                series,
                label=legend_label,
                marker=marker,
                line_style=line_style,
            )

        if plotted_count == 0:
            skipped.append(
                f"{path}: all {len(series)} samples are missing for "
                f"station={station!r}, parameter={parameter!r}, interval=[{begin}, {end})"
            )
            continue
        total_plotted += plotted_count

    for message in skipped:
        print(f"[WARNING] {message}")

    if total_plotted == 0:
        raise SystemExit(
            f"No plottable samples found for station={station!r}, "
            f"parameter={parameter!r}, interval=[{begin}, {end}) in "
            f"{len(sinex_items)} file(s)."
        )

    parameter_label = PARAMETER_DESCRIPTIONS.get(parameter, parameter)
    source_note = f" ({len(sinex_items)} files)" if multiple_files else ""
    ax.set_title(f"{station.upper()} {parameter}: {parameter_label}{source_note}")
    ax.set_xlabel("Epoch")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    format_time_axis(ax)

    if parameter == "STDDEV" or multiple_files or len(ax.lines) > 1:
        ax.legend(loc="best")

    fig.tight_layout()

    if output:
        output_path = Path(output)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
        print(f"Saved plot to {output_path}")
    else:
        plt.show()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    sinex_items = [
        (Path(filename), TropoSinex(filename))
        for filename in args.tropo_sinex_files
    ]

    if args.list_available:
        for path, sinex in sinex_items:
            print(f"[{path}]")
            print("  Available parameters:", ", ".join(sinex.available_parameters()))
            print("  Available sites:", ", ".join(sinex.available_sites()))

    begin = datetime.datetime.min if args.begin is None else args.begin
    end = datetime.datetime.max if args.end is None else args.end

    make_plot(
        sinex_items=sinex_items,
        station=args.station,
        parameter=args.parameter,
        begin=begin,
        end=end,
        output=args.output,
        dpi=args.dpi,
        marker=args.marker,
        line_style=args.line_style,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
