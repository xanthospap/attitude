#!/usr/bin/env python3
"""
merge_sp3c_single_sat.py

Merge multiple SP3-c files that each contain exactly one satellite into one
SP3-c file for a requested date/time range.

The script intentionally ignores multi-satellite SP3-c files such as normal
GNSS orbit products. It rebuilds the SP3-c header so the output contains a
single-satellite satellite list and the correct start epoch / epoch count.

Examples
--------
  python merge_sp3c_single_sat.py -o out.sp3 \
      --start 2024-01-01 --end 2024-01-07 \
      day001.sp3 day002.sp3 day003.sp3

  python merge_sp3c_single_sat.py -o out.sp3 --sat L39 \
      --start "2024-01-01T12:00:00" --end "2024-01-02T12:00:00" \
      *.sp3

Notes
-----
- Input files must be SP3-c, i.e. the first two characters of line 1 are '#c'.
- Only files whose header satellite count/list resolves to exactly one
  satellite are used. Multi-satellite files are ignored.
- The script preserves epoch records verbatim, including optional EP/EV records.
- Date/time comparisons are naive and are assumed to use the SP3 file's own
  time system. No GPS/UTC/TAI leap-second conversion is attempted.
- Plain text and .gz files are supported. Unix .Z files are not decompressed.
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

GPS_EPOCH = datetime(1980, 1, 6)
MJD_EPOCH = datetime(1858, 11, 17)


@dataclass
class EpochBlock:
    epoch: datetime
    records: List[str]


@dataclass
class Sp3File:
    path: Path
    header: List[str]
    sat_id: str
    accuracy: int
    pv_flag: str
    coord_sys: str
    time_system: str
    interval: float
    epochs: List[EpochBlock]


class Sp3Error(Exception):
    pass


class IgnoredFile(Exception):
    pass


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def pad(line: str, width: int = 60) -> str:
    """Return a line without newline, padded to at least width characters."""
    return line.rstrip("\r\n").ljust(width)


def open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="ascii", errors="replace", newline=None)
    return open(path, "rt", encoding="ascii", errors="replace", newline=None)


def parse_decimal_second(value: str) -> Tuple[int, int]:
    """Return (whole_seconds, microseconds), rounded from a decimal seconds field."""
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise Sp3Error(f"bad seconds field: {value!r}") from exc

    whole = int(dec)  # Decimal int truncates toward zero; seconds are non-negative here.
    frac = dec - Decimal(whole)
    micros = int((frac * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))
    if micros >= 1_000_000:
        whole += 1
        micros -= 1_000_000
    return whole, micros


def make_datetime(year: int, month: int, day: int, hour: int, minute: int, second_field: str) -> datetime:
    second, microsecond = parse_decimal_second(second_field)

    # Python's datetime has no second=60. Represent a leap-second label as the
    # first instant of the next minute. This is only for ordering/filtering.
    if second == 60:
        return datetime(year, month, day, hour, minute, 59, microsecond) + timedelta(seconds=1)
    return datetime(year, month, day, hour, minute, second, microsecond)


def parse_epoch_line(line: str) -> datetime:
    parts = line.split()
    if len(parts) < 7 or parts[0] != "*":
        raise Sp3Error(f"bad epoch line: {line!r}")
    return make_datetime(
        int(parts[1]), int(parts[2]), int(parts[3]),
        int(parts[4]), int(parts[5]), parts[6]
    )


def normalize_sat_id(raw: str) -> str:
    s = raw.strip().upper()
    m = re.fullmatch(r"([A-Z])(\d{1,2})", s)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}"
    return s


def parse_cli_datetime(raw: str, is_end: bool) -> datetime:
    s = raw.strip()

    # Date-only arguments are convenient for whole-day ranges.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = date.fromisoformat(s)
        return datetime.combine(d, time.max if is_end else time.min)

    # ISO-like input, with optional trailing Z. We keep it naive because SP3's
    # time system is declared in the header and may be GPS/UTC/TAI/etc.
    iso = s[:-1] if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso.replace("T", " "))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    # SP3-style input: YYYY MM DD HH MM SS.ssssssss
    parts = s.replace(",", " ").split()
    if len(parts) == 6:
        try:
            return make_datetime(
                int(parts[0]), int(parts[1]), int(parts[2]),
                int(parts[3]), int(parts[4]), parts[5]
            )
        except (ValueError, Sp3Error) as exc:
            raise argparse.ArgumentTypeError(f"invalid datetime {raw!r}") from exc

    raise argparse.ArgumentTypeError(
        f"invalid datetime {raw!r}; use YYYY-MM-DD, ISO datetime, or 'YYYY MM DD HH MM SS.s'"
    )


def parse_sat_ids(header: Sequence[str]) -> List[str]:
    ids: List[str] = []
    for raw in header[2:7]:
        line = pad(raw)
        # Satellite IDs occupy 17 consecutive A1,I2.2 fields after columns 1-9.
        for i in range(17):
            token = line[9 + 3 * i: 12 + 3 * i]
            stripped = token.strip()
            if stripped and stripped != "0":
                ids.append(token)
    return ids


def parse_sat_count(header: Sequence[str]) -> Optional[int]:
    if len(header) < 3:
        return None
    field = pad(header[2])[4:6].strip()
    try:
        return int(field)
    except ValueError:
        return None


def parse_accuracy(header: Sequence[str], sat_id: str) -> int:
    ids: List[str] = []
    for raw in header[2:7]:
        line = pad(raw)
        for i in range(17):
            ids.append(line[9 + 3 * i: 12 + 3 * i])

    try:
        idx = ids.index(sat_id)
    except ValueError:
        return 0

    acc_values: List[int] = []
    for raw in header[7:12]:
        line = pad(raw)
        for i in range(17):
            field = line[9 + 3 * i: 12 + 3 * i].strip()
            try:
                acc_values.append(int(field) if field else 0)
            except ValueError:
                acc_values.append(0)

    return acc_values[idx] if idx < len(acc_values) else 0


def parse_interval(header: Sequence[str]) -> float:
    if len(header) < 2:
        return 0.0
    field = pad(header[1])[24:38].strip()
    try:
        return float(field)
    except ValueError:
        return 0.0


def read_sp3c_single_sat(path: Path) -> Sp3File:
    try:
        with open_text(path) as f:
            lines = [line.rstrip("\r\n") for line in f]
    except OSError as exc:
        raise IgnoredFile(f"cannot read {path}: {exc}") from exc

    if not lines:
        raise IgnoredFile(f"empty file: {path}")
    if not lines[0].startswith("#c"):
        raise IgnoredFile(f"not SP3-c: {path}")

    first_epoch_idx = next((i for i, line in enumerate(lines) if line.startswith("*")), None)
    if first_epoch_idx is None:
        raise IgnoredFile(f"no epoch records: {path}")

    header = lines[:first_epoch_idx]
    if len(header) < 22:
        raise IgnoredFile(f"header has fewer than 22 SP3-c lines: {path}")

    sat_count = parse_sat_count(header)
    sat_ids = parse_sat_ids(header)
    if sat_count != 1 or len(sat_ids) != 1:
        raise IgnoredFile(f"multi-satellite or malformed satellite list: {path}")

    sat_id = sat_ids[0]
    pv_flag = pad(header[0])[2]
    if pv_flag not in {"P", "V"}:
        raise IgnoredFile(f"bad position/velocity flag {pv_flag!r}: {path}")

    coord_sys = pad(header[0])[46:51]
    time_system = pad(header[12])[9:12] if len(header) > 12 else "   "
    accuracy = parse_accuracy(header, sat_id)
    interval = parse_interval(header)

    epochs: List[EpochBlock] = []
    i = first_epoch_idx
    while i < len(lines):
        line = lines[i]
        if line.startswith("EOF"):
            break
        if not line.startswith("*"):
            i += 1
            continue

        epoch = parse_epoch_line(line)
        i += 1
        records: List[str] = []
        while i < len(lines) and not lines[i].startswith("*") and not lines[i].startswith("EOF"):
            if lines[i] != "":
                records.append(lines[i])
            i += 1

        p_records = [r for r in records if r.startswith("P") and not r.startswith("EP")]
        v_records = [r for r in records if r.startswith("V") and not r.startswith("EV")]
        p_sats = [pad(r, 4)[1:4] for r in p_records]
        v_sats = [pad(r, 4)[1:4] for r in v_records]

        if len(p_records) != 1 or p_sats[0] != sat_id:
            raise IgnoredFile(f"epoch with missing/wrong P record in {path}")
        if pv_flag == "V" and (len(v_records) != 1 or v_sats[0] != sat_id):
            raise IgnoredFile(f"V-mode file has epoch without matching V record in {path}")
        if pv_flag == "P" and v_records:
            raise IgnoredFile(f"P-mode file unexpectedly contains V records in {path}")

        epochs.append(EpochBlock(epoch=epoch, records=records))

    return Sp3File(
        path=path,
        header=header[:22],
        sat_id=sat_id,
        accuracy=accuracy,
        pv_flag=pv_flag,
        coord_sys=coord_sys,
        time_system=time_system,
        interval=interval,
        epochs=epochs,
    )


def seconds_of_day(dt: datetime) -> float:
    return dt.hour * 3600.0 + dt.minute * 60.0 + dt.second + dt.microsecond / 1_000_000.0


def gps_week_sow(dt: datetime) -> Tuple[int, float]:
    delta = dt - GPS_EPOCH
    total = delta.total_seconds()
    week = int(total // (7 * 86400))
    sow = total - week * 7 * 86400
    return week, sow


def mjd_and_fraction(dt: datetime) -> Tuple[int, float]:
    mjd = (datetime(dt.year, dt.month, dt.day) - MJD_EPOCH).days
    return mjd, seconds_of_day(dt) / 86400.0


def format_epoch_time(dt: datetime) -> Tuple[int, int, int, int, int, float]:
    sec = dt.second + dt.microsecond / 1_000_000.0
    return dt.year, dt.month, dt.day, dt.hour, dt.minute, sec


def format_sp3_epoch_line(dt: datetime) -> str:
    y, mo, d, h, mi, sec = format_epoch_time(dt)
    return f"*  {y:4d} {mo:2d} {d:2d} {h:2d} {mi:2d} {sec:011.8f}"


def format_comment(text: str) -> str:
    return "/* " + text[:57].ljust(57)


def infer_output_interval(epoch_times: Sequence[datetime], fallback: float) -> float:
    if len(epoch_times) < 2:
        return fallback
    deltas = [round((b - a).total_seconds(), 8) for a, b in zip(epoch_times, epoch_times[1:])]
    positive = [d for d in deltas if d > 0]
    if not positive:
        return fallback
    counts = Counter(positive)
    interval = counts.most_common(1)[0][0]
    if len(counts) > 1:
        warn(
            "output epochs are not perfectly regular; "
            f"header interval set to most common delta {interval:.8f} seconds"
        )
    return interval


def build_satellite_lines(sat_id: str, accuracy: int) -> List[str]:
    sats = [sat_id] + ["  0"] * 84
    accs = [accuracy] + [0] * 84

    lines: List[str] = []
    for row in range(5):
        prefix = f"+   {1:2d}   " if row == 0 else "+        "
        chunk = "".join(sats[row * 17:(row + 1) * 17])
        lines.append((prefix + chunk).ljust(60)[:60])

    for row in range(5):
        prefix = "++       "
        chunk = "".join(f"{value:3d}" for value in accs[row * 17:(row + 1) * 17])
        lines.append((prefix + chunk).ljust(60)[:60])

    return lines


def build_header(template: Sp3File, sat_id: str, accuracy: int, start_epoch: datetime,
                 num_epochs: int, interval: float, requested_start: datetime,
                 requested_end: datetime) -> List[str]:
    h0 = pad(template.header[0])
    pv_flag = h0[2]
    data_used = h0[40:45]
    coord_sys = h0[46:51]
    orbit_type = h0[52:55]
    agency = h0[56:60]

    y, mo, d, h, mi, sec = format_epoch_time(start_epoch)
    line1 = (
        f"#c{pv_flag}{y:4d} {mo:2d} {d:2d} {h:2d} {mi:2d} {sec:011.8f} "
        f"{num_epochs:7d} {data_used:5s} {coord_sys:5s} {orbit_type:3s} {agency:4s}"
    )[:60]

    week, sow = gps_week_sow(start_epoch)
    mjd, frac = mjd_and_fraction(start_epoch)
    line2 = f"## {week:4d} {sow:15.8f} {interval:14.8f} {mjd:5d} {frac:15.13f}"[:60]

    sat_acc_lines = build_satellite_lines(sat_id, accuracy)

    # Preserve SP3-c metadata records 13-18 from the template. These contain
    # file type/time system and accuracy exponent bases.
    meta = [pad(line)[:60] for line in template.header[12:18]]
    while len(meta) < 6:
        meta.append("%c".ljust(60)[:60] if len(meta) < 2 else "%f".ljust(60)[:60])

    comments = [
        format_comment("MERGED SINGLE-SATELLITE SP3-C FILE"),
        format_comment(f"SAT {sat_id}; EPOCHS {num_epochs}"),
        format_comment(f"RANGE {requested_start.isoformat()} TO {requested_end.isoformat()}"),
        format_comment(f"TEMPLATE {template.path.name}"),
    ]

    header = [line1, line2] + sat_acc_lines[:10] + meta[:6] + comments[:4]
    if len(header) != 22:
        raise AssertionError(f"internal error: built {len(header)} header lines, expected 22")
    return header


def compatible(a: Sp3File, b: Sp3File) -> Tuple[bool, str]:
    if a.pv_flag != b.pv_flag:
        return False, f"P/V flag differs ({a.pv_flag!r} vs {b.pv_flag!r})"
    if a.coord_sys != b.coord_sys:
        return False, f"coordinate system differs ({a.coord_sys!r} vs {b.coord_sys!r})"
    if a.time_system != b.time_system:
        return False, f"time system differs ({a.time_system!r} vs {b.time_system!r})"
    return True, ""


def collect_files(paths: Iterable[Path]) -> List[Sp3File]:
    files: List[Sp3File] = []
    for path in paths:
        try:
            files.append(read_sp3c_single_sat(path))
        except IgnoredFile as exc:
            warn(str(exc))
    return files


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge single-satellite SP3-c files over a date/time range. Multi-satellite files are ignored."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="input .sp3/.sp3c text files, optionally .gz")
    parser.add_argument("-o", "--output", required=True, type=Path, help="output SP3-c file")
    parser.add_argument("--start", required=True, help="inclusive start: YYYY-MM-DD, ISO datetime, or SP3-style fields")
    parser.add_argument("--end", required=True, help="inclusive end by default; date-only means end of that day")
    parser.add_argument("--exclusive-end", action="store_true", help="treat --end as exclusive instead of inclusive")
    parser.add_argument("--sat", help="satellite ID to merge, e.g. L39, G01; otherwise inferred if unambiguous")
    parser.add_argument("--overwrite", action="store_true", help="overwrite output if it exists")
    args = parser.parse_args(argv)

    start = parse_cli_datetime(args.start, is_end=False)
    end = parse_cli_datetime(args.end, is_end=True)
    if end < start:
        parser.error("--end must be greater than or equal to --start")

    if args.output.exists() and not args.overwrite:
        parser.error(f"output exists: {args.output}; use --overwrite to replace it")

    sp3_files = collect_files(args.inputs)
    if not sp3_files:
        parser.error("no usable single-satellite SP3-c input files found")

    if args.sat:
        sat_id = normalize_sat_id(args.sat)
        if len(sat_id) != 3:
            parser.error("--sat must be a three-character SP3 satellite ID such as G01 or L39")
    else:
        sat_ids = sorted({f.sat_id for f in sp3_files})
        if len(sat_ids) != 1:
            parser.error(f"found multiple single-satellite IDs {sat_ids}; rerun with --sat")
        sat_id = sat_ids[0]

    selected = [f for f in sp3_files if f.sat_id == sat_id]
    if not selected:
        parser.error(f"no usable single-satellite SP3-c input files found for satellite {sat_id}")

    template = selected[0]
    compatible_selected: List[Sp3File] = []
    for f in selected:
        ok, reason = compatible(template, f)
        if ok:
            compatible_selected.append(f)
        else:
            warn(f"ignoring {f.path}: incompatible with template {template.path}: {reason}")

    if not compatible_selected:
        parser.error("no compatible input files remain after metadata checks")

    # Collect and de-duplicate epochs. Later input files override earlier ones for
    # exactly duplicate epoch timestamps.
    by_epoch: dict[datetime, EpochBlock] = {}
    duplicate_count = 0
    for f in compatible_selected:
        for block in f.epochs:
            in_range = start <= block.epoch < end if args.exclusive_end else start <= block.epoch <= end
            if not in_range:
                continue
            if block.epoch in by_epoch:
                duplicate_count += 1
            by_epoch[block.epoch] = block

    if not by_epoch:
        parser.error(f"no epochs for satellite {sat_id} in requested range")

    epoch_times = sorted(by_epoch)
    if duplicate_count:
        warn(f"replaced {duplicate_count} duplicate epoch(s) with later input occurrence(s)")

    interval = infer_output_interval(epoch_times, template.interval)
    accuracy = template.accuracy
    header = build_header(
        template=template,
        sat_id=sat_id,
        accuracy=accuracy,
        start_epoch=epoch_times[0],
        num_epochs=len(epoch_times),
        interval=interval,
        requested_start=start,
        requested_end=end,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wt", encoding="ascii", newline="\n") as out:
        for line in header:
            out.write(line.rstrip() + "\n")
        for epoch in epoch_times:
            out.write(format_sp3_epoch_line(epoch).rstrip() + "\n")
            for rec in by_epoch[epoch].records:
                out.write(rec.rstrip() + "\n")
        out.write("EOF\n")

    print(
        f"wrote {args.output} with {len(epoch_times)} epochs for {sat_id} "
        f"from {len(compatible_selected)} input file(s)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
