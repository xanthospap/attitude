from __future__ import annotations

import logging
import tarfile
from pathlib import Path

import astropy.time as atime
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

from parsers.cryosat_attitude import read_cryosat_quaternion_file
from parsers.swot_attitude import read_swot_qsolp_xml


logger = logging.getLogger(__name__)


JASON_SATELLITES = {"ja1", "ja2", "ja3"}
SENTINEL_SATELLITES = {"s3a", "s3b", "s6a"}
SWOT_SATELLITES = {"swo"}
CRYOSAT_SATELLITES = {"cs2"}

SUPPORTED_SATELLITES = (
    JASON_SATELLITES
    | SENTINEL_SATELLITES
    | SWOT_SATELLITES
    | CRYOSAT_SATELLITES
)

QUATERNION_COLUMNS = ["q0", "q1", "q2", "q3"]
SOLAR_PANEL_COLUMNS = ["left_panel", "right_panel"]


def _name(path: str | Path) -> str:
    return Path(path).name.lower()


def _is_qbody(path: str | Path) -> bool:
    return "qbody" in _name(path) or "body" in _name(path)


def _is_qsolp(path: str | Path) -> bool:
    return "qsolp" in _name(path) or "solp" in _name(path)


def _read_text_attitude_file(
    qfile: str | Path,
    usecols: list[int],
    names: list[str],
) -> pd.DataFrame:
    qfile = Path(qfile)

    df = pd.read_csv(
        qfile,
        sep=r"\s+",
        comment="#",
        header=None,
        usecols=usecols,
        names=names,
    )

    df["date_time"] = pd.to_datetime(
        df["_date"].astype(str) + " " + df["_time"].astype(str),
        format="%Y/%m/%d %H:%M:%S.%f",
    )

    return df.drop(columns=["_date", "_time"])


def read_attitude_file(satellite: str, qfile: str | Path) -> pd.DataFrame:
    """
    Read one local attitude file.

    Output columns are either:
        date_time, q0, q1, q2, q3

    or:
        date_time, left_panel, right_panel
    """

    satellite = satellite.lower()
    qfile = Path(qfile)
    name = qfile.name.lower()

    logger.info("Reading attitude file %s", qfile)

    if satellite not in SUPPORTED_SATELLITES:
        raise ValueError(f"Unsupported satellite: {satellite}")

    if satellite == "swo" and _is_qsolp(name):
        return read_swot_qsolp_xml(qfile)

    if satellite in CRYOSAT_SATELLITES:
        return read_cryosat_quaternion_file(qfile)

    if satellite == "ja1":
        if _is_qbody(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 2, 3, 4, 5],
                names=["_date", "_time", *QUATERNION_COLUMNS],
            )

        if _is_qsolp(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 2, 3],
                names=["_date", "_time", *SOLAR_PANEL_COLUMNS],
            )

        raise ValueError(f"Cannot identify Jason-1 attitude file type: {qfile}")

    if satellite in {"ja2", "ja3", "swo"}:
        if _is_qbody(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 3, 6, 9, 12],
                names=["_date", "_time", *QUATERNION_COLUMNS],
            )

        if _is_qsolp(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 3, 6],
                names=["_date", "_time", *SOLAR_PANEL_COLUMNS],
            )

        raise ValueError(f"Cannot identify attitude file type: {qfile}")

    if satellite in SENTINEL_SATELLITES:
        return _read_text_attitude_file(
            qfile,
            usecols=[0, 1, 2, 3, 4, 5],
            names=["_date", "_time", *QUATERNION_COLUMNS],
        )

    raise ValueError(f"Unsupported satellite: {satellite}")


def _fix_time(satellite: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert input times to TT datetime64 and set them as the dataframe index.

    Jason and SWOT files are treated as UTC.
    Sentinel files are treated as GPST, represented as TAI after adding 19 seconds.
    CryoSat-2 AUX_PROQUA data-block times are treated as TAI.
    """

    satellite = satellite.lower()

    if satellite in JASON_SATELLITES | SWOT_SATELLITES:
        tt = atime.Time(df["date_time"].to_numpy(), scale="utc").tt

    elif satellite in SENTINEL_SATELLITES:
        tai_datetimes = df["date_time"] + np.timedelta64(19, "s")
        tt = atime.Time(tai_datetimes.to_numpy(), scale="tai").tt

    elif satellite in CRYOSAT_SATELLITES:
        tt = atime.Time(df["date_time"].to_numpy(), scale="tai").tt

    else:
        raise ValueError(f"Unsupported satellite: {satellite}")

    df = df.copy()
    df["date_time"] = tt.to_value(format="datetime64")

    return df.set_index("date_time")


def _time_to_mjd_and_sod(
    time_array, scale: str = "tt"
) -> tuple[np.ndarray, np.ndarray]:
    t = atime.Time(time_array, format="datetime64", scale=scale)
    mjd_days = t.mjd.astype(int)
    sec_of_day = (t.mjd - mjd_days) * 86400.0

    return mjd_days, sec_of_day

def _deduplicate_attitude(df: pd.DataFrame) -> pd.DataFrame:
    """Return records in strict epoch order with exact duplicates removed.

    Sorting is stable so that, for duplicate epochs coming from overlapping
    products, ``keep="last"`` deterministically keeps the later input record.
    Quaternion records are never averaged.
    """

    df = df.sort_index(kind="stable")
    num_duplicates = int(df.index.duplicated(keep="last").sum())
    if num_duplicates:
        logger.info("Removing %d duplicate attitude epoch(s)", num_duplicates)
    df = df[~df.index.duplicated(keep="last")]

    if not df.index.is_unique or not df.index.is_monotonic_increasing:
        raise RuntimeError("Failed to construct strictly ordered attitude epochs")

    return df


def _native_attitude(df: pd.DataFrame) -> pd.DataFrame:
    """Keep native source epochs; only sort and remove exact duplicates."""

    return _deduplicate_attitude(df)


def _interpolate(
    df: pd.DataFrame,
    nsec: float | None,
    times: np.ndarray | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Interpolate either body quaternions or solar-panel angles.

    Quaternion interpolation uses SLERP.
    Solar-panel interpolation is linear in time.
    """

    if df.empty:
        raise ValueError("Cannot interpolate an empty dataframe")

    # df = df.sort_index().groupby(df.index).mean()
    df = _deduplicate_attitude(df)

    source_times = atime.Time(df.index.values, scale="tt").mjd

    if len(source_times) < 2:
        raise ValueError("At least two unique attitude epochs are required for interpolation")

    if times is None:
        if nsec is None or nsec <= 0:
            raise ValueError("Interpolation interval nsec must be positive")
        step = nsec / 86400.0
        n_steps = int(np.floor((source_times[-1] - source_times[0]) / step)) + 1
        times = source_times[0] + np.arange(n_steps, dtype=float) * step
        times = times[times <= source_times[-1]]

    if all(col in df.columns for col in QUATERNION_COLUMNS):
        logger.info("Interpolating body quaternions")

        quaternions = df[QUATERNION_COLUMNS].to_numpy()

        rotations = R.from_quat(quaternions, scalar_first=True)
        slerp = Slerp(source_times, rotations)
        interpolated = slerp(times)

        out = pd.DataFrame(
            data=interpolated.as_quat(scalar_first=True),
            index=times,
            columns=QUATERNION_COLUMNS,
        )

    elif all(col in df.columns for col in SOLAR_PANEL_COLUMNS):
        logger.info("Interpolating solar-panel angles")

        numeric = pd.DataFrame(
            data=df[SOLAR_PANEL_COLUMNS].to_numpy(),
            index=source_times,
            columns=SOLAR_PANEL_COLUMNS,
        )

        target_index = pd.Index(times, name="mjd")

        out = (
            numeric.reindex(numeric.index.union(target_index))
            .sort_index()
            .interpolate(method="index")
            .loc[target_index]
        )

    else:
        raise ValueError(
            "Input dataframe has neither quaternion columns nor solar-panel columns"
        )

    out.index = atime.Time(
        out.index.to_numpy(),
        format="mjd",
        scale="tt",
    ).to_value(format="datetime64")

    return out, times


def _fill_native_component(
    source: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    *,
    component_name: str,
) -> pd.DataFrame:
    """Preserve native records and interpolate only missing target epochs.

    ``target_index`` is normally the union of the body and panel source epochs.
    Existing source values are copied unchanged.  Only epochs absent from this
    component are interpolated.  Extrapolation is deliberately forbidden: if
    the other component has a raw epoch outside this component's coverage, we
    fail rather than silently discard or invent an endpoint value.
    """

    source = _native_attitude(source)
    missing = target_index[~target_index.isin(source.index)]
    out = source.reindex(target_index)

    if len(missing) == 0:
        logger.info(
            "Native %s epochs already match all %d output epoch(s)",
            component_name,
            len(target_index),
        )
        return out

    if len(source) < 2:
        raise ValueError(
            f"Cannot interpolate {component_name}: fewer than two unique source epochs"
        )

    if missing[0] < source.index[0] or missing[-1] > source.index[-1]:
        raise ValueError(
            f"Cannot preserve all native attitude records: {component_name} "
            "does not bracket all epochs from the other attitude component"
        )

    logger.info(
        "Interpolating %s at %d unmatched native epoch(s); source records remain unchanged",
        component_name,
        len(missing),
    )

    target_mjd = atime.Time(
        missing.to_numpy(),
        format="datetime64",
        scale="tt",
    ).mjd
    interpolated, _ = _interpolate(source, nsec=None, times=target_mjd)
    out.loc[missing, source.columns] = interpolated[source.columns].to_numpy()
    return out


def _merge_native_body_and_panel(
    satellite: str,
    df_body: pd.DataFrame,
    df_panel: pd.DataFrame,
    *,
    start=None,
    end=None,
) -> pd.DataFrame:
    """Merge body/panel streams on every native epoch in the output interval.

    Records outside the requested interval remain available as interpolation
    brackets but are not themselves output.  This is important when body and
    panel timestamps are offset and have no exact matches inside the interval.
    """

    df_body = _native_attitude(df_body)
    df_panel = _native_attitude(df_panel)
    epochs = df_body.index.union(df_panel.index).sort_values()

    if start is not None:
        start_tt = atime.Time(start, scale="utc").tt.to_value(format="datetime64")
        epochs = epochs[epochs >= start_tt]
    if end is not None:
        end_tt = atime.Time(end, scale="utc").tt.to_value(format="datetime64")
        epochs = epochs[epochs < end_tt]

    if len(epochs) == 0:
        raise ValueError(f"No native attitude epochs remain for {satellite}")

    body_interpolations = int((~epochs.isin(df_body.index)).sum())
    panel_interpolations = int((~epochs.isin(df_panel.index)).sum())
    logger.info(
        "Native %s attitude merge: %d body epoch(s), %d panel epoch(s), "
        "%d unique output epoch(s)",
        satellite,
        len(df_body),
        len(df_panel),
        len(epochs),
    )

    body = _fill_native_component(
        df_body,
        epochs,
        component_name="body quaternions",
    )
    panel = _fill_native_component(
        df_panel,
        epochs,
        component_name="solar-panel angles",
    )

    merged = pd.concat([body, panel], axis=1)
    merged = _deduplicate_attitude(merged)

    if len(merged) != len(epochs):
        raise RuntimeError("Native body/panel merge lost attitude epochs")

    logger.info(
        "Native %s merge kept every unique raw epoch; interpolated %d body and "
        "%d panel component value(s)",
        satellite,
        body_interpolations,
        panel_interpolations,
    )
    return merged


def _to_output_index(df: pd.DataFrame) -> pd.DataFrame:
    mjd_days, sec_of_day = _time_to_mjd_and_sod(df.index.values, scale="tt")

    df = df.copy()
    df["MJDay"] = mjd_days
    df["SecOfDay"] = sec_of_day

    return df.reset_index(drop=True).set_index(["MJDay", "SecOfDay"])


def _extract_sentinel_dbl_files(files: list[Path]) -> list[Path]:
    """
    Extract Sentinel DBL files from tar archives.

    If an input file is already a .DBL file, keep it.
    """

    extracted: list[Path] = []

    for file in files:
        file = Path(file)

        if file.name.upper().endswith(".DBL"):
            extracted.append(file)
            continue

        target_dir = file.parent

        with tarfile.open(file, "r:*") as archive:
            for member in archive.getmembers():
                if not member.name.upper().endswith(".DBL"):
                    continue

                archive.extract(member, path=target_dir, filter="data")

                extracted_file = target_dir / member.name
                extracted.append(extracted_file)

                logger.debug("Extracted %s from %s", member.name, file)

    return extracted


def _matching_qsolp_file(qbody_file: Path, files_by_name: dict[str, Path]) -> Path:
    expected_name = qbody_file.name.lower().replace("qbody", "qsolp")

    if expected_name in files_by_name:
        return files_by_name[expected_name]

    expected_file = qbody_file.with_name(qbody_file.name.replace("qbody", "qsolp"))

    if expected_file.exists():
        return expected_file

    raise FileNotFoundError(
        f"Could not find solar-panel file matching body file {qbody_file}. "
        f"Expected {expected_name}"
    )


def _process_body_and_panel_files(
    satellite: str,
    body_files: list[Path],
    panel_files: list[Path],
    nsec: float | None,
    *,
    start=None,
    end=None,
) -> pd.DataFrame:
    if not body_files:
        raise ValueError(f"No qbody files found for {satellite}")

    if not panel_files:
        raise ValueError(f"No qsolp files found for {satellite}")

    body_dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file)) for file in body_files
    ]

    panel_dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file))
        for file in panel_files
    ]

    source_body = pd.concat(body_dfs)
    source_panel = pd.concat(panel_dfs)

    if nsec is None:
        merged = _merge_native_body_and_panel(
            satellite,
            source_body,
            source_panel,
            start=start,
            end=end,
        )
    else:
        df_body, times = _interpolate(source_body, nsec)
        df_panel, _ = _interpolate(source_panel, nsec, times=times)
        merged = pd.merge(
            df_body,
            df_panel,
            left_index=True,
            right_index=True,
            validate="one_to_one",
        )

    return _to_output_index(_deduplicate_attitude(merged))


def _process_jason_files(
    satellite: str,
    nsec: float | None,
    qfns: list[str | Path],
    *,
    start=None,
    end=None,
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]
    files_by_name = {file.name.lower(): file for file in files}

    body_files = sorted(file for file in files if _is_qbody(file))
    panel_files = [_matching_qsolp_file(file, files_by_name) for file in body_files]

    return _process_body_and_panel_files(
        satellite=satellite,
        body_files=body_files,
        panel_files=panel_files,
        nsec=nsec,
        start=start,
        end=end,
    )


def _process_swot_files(
    satellite: str,
    nsec: float | None,
    qfns: list[str | Path],
    *,
    start=None,
    end=None,
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]

    body_files = sorted(file for file in files if _is_qbody(file))
    panel_files = sorted(file for file in files if _is_qsolp(file))

    return _process_body_and_panel_files(
        satellite=satellite,
        body_files=body_files,
        panel_files=panel_files,
        nsec=nsec,
        start=start,
        end=end,
    )


def _process_cryosat_files(
    satellite: str,
    nsec: float | None,
    qfns: list[str | Path],
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]

    dfs = [_fix_time(satellite, read_attitude_file(satellite, file)) for file in files]

    source = pd.concat(dfs)
    if nsec is None:
        logger.info("Keeping native %s attitude epochs (no resampling)", satellite)
        df = _native_attitude(source)
    else:
        df, _ = _interpolate(source, nsec)
    return _to_output_index(df)


def _process_sentinel_files(
    satellite: str,
    nsec: float | None,
    qfns: list[str | Path],
    cleanup_extracted: bool = True,
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]
    attitude_files = _extract_sentinel_dbl_files(files)

    if not attitude_files:
        raise ValueError(f"No Sentinel DBL files found for {satellite}")

    dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file))
        for file in attitude_files
    ]

    source = pd.concat(dfs)
    if nsec is None:
        logger.info("Keeping native %s attitude epochs (no resampling)", satellite)
        df = _native_attitude(source)
    else:
        df, _ = _interpolate(source, nsec)
    df = _to_output_index(df)

    if cleanup_extracted:
        original_files = {file.resolve() for file in files}

        for file in attitude_files:
            try:
                if file.resolve() not in original_files:
                    file.unlink()
            except FileNotFoundError:
                pass

    return df


def _clip_output_range(
    df: pd.DataFrame,
    start=None,
    end=None,
    requested_time_scale: str = "utc",
) -> pd.DataFrame:
    """
    Clip output dataframe indexed by TT (MJDay, SecOfDay) to [start, end).

    CLI/YAML request datetimes are interpreted as UTC by default and converted
    to TT before comparison.  This avoids dropping/keeping samples off by the
    current UTC-to-TT offset.
    """

    if start is None and end is None:
        return df

    index_mjd = (
        df.index.get_level_values("MJDay").to_numpy(dtype=float)
        + df.index.get_level_values("SecOfDay").to_numpy(dtype=float) / 86400.0
    )

    mask = np.ones(len(df), dtype=bool)

    if start is not None:
        start_mjd = atime.Time(start, scale=requested_time_scale).tt.mjd
        mask &= index_mjd >= start_mjd

    if end is not None:
        end_mjd = atime.Time(end, scale=requested_time_scale).tt.mjd
        mask &= index_mjd < end_mjd

    return df.loc[mask]


def _validate_output_epoch_order(df: pd.DataFrame) -> None:
    """Guarantee unique, strictly increasing epochs in the written product."""

    if not df.index.is_unique:
        raise RuntimeError("Prepared attitude output contains duplicate epochs")

    if len(df) < 2:
        return

    days = df.index.get_level_values("MJDay").to_numpy(dtype=np.int64)
    sod = df.index.get_level_values("SecOfDay").to_numpy(dtype=float)
    strictly_later = (days[1:] > days[:-1]) | (
        (days[1:] == days[:-1]) & (sod[1:] > sod[:-1])
    )
    if not np.all(strictly_later):
        raise RuntimeError(
            "Prepared attitude output epochs are not strictly chronological"
        )


def preprocess_attitude(
    satellite: str,
    qfns: list[str | Path],
    nsec: float | None = None,
    start=None,
    end=None,
    output_file: str | Path | None = None,
) -> Path:
    """
    Process local attitude files and write the canonical output CSV.

    By default, source epochs are preserved.  For missions with separate body
    and solar-panel streams, the output epoch set is the union of both native
    streams; only the missing component is interpolated at unmatched epochs.
    Supplying ``nsec`` explicitly instead requests uniform resampling.

    This function does not download anything.
    """

    satellite = satellite.lower()
    files = [Path(file) for file in qfns]

    if not files:
        raise ValueError(f"No attitude files provided for satellite {satellite}")

    if satellite in JASON_SATELLITES:
        df = _process_jason_files(
            satellite, nsec, files, start=start, end=end
        )

    elif satellite in SENTINEL_SATELLITES:
        df = _process_sentinel_files(satellite, nsec, files)

    elif satellite in SWOT_SATELLITES:
        df = _process_swot_files(
            satellite, nsec, files, start=start, end=end
        )

    elif satellite in CRYOSAT_SATELLITES:
        df = _process_cryosat_files(satellite, nsec, files)

    else:
        raise ValueError(f"Unsupported satellite: {satellite}")

    if start is not None or end is not None:
        df = _clip_output_range(df, start=start, end=end)

    if output_file is None:
        output_file = files[0].parent / f"qua_{satellite}.csv"
    else:
        output_file = Path(output_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Writing preprocessed attitude file to %s", output_file)

    if nsec is None and df.isna().any().any():
        raise ValueError(
            "Native attitude output contains missing component values; "
            "all raw epochs must be retained with complete records"
        )

    # Preserve the legacy behavior for explicitly resampled products, where a
    # non-bracketed edge sample may remain NaN and is omitted.  Native mode
    # never silently drops a raw epoch.
    df = df.dropna()
    _validate_output_epoch_order(df)

    df.to_csv(
        output_file,
        sep=" ",
        float_format="%.12e",
        header=False,
    )

    return output_file


# Backwards-compatible alias while refactoring callers.
preprocess = preprocess_attitude
