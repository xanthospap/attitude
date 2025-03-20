# -*- coding: utf-8 -*-

"""preprocess.py

[Uncompress,] read, interpolate and concatenate quaternion files.
"""

# import glob
import logging
import pathlib
import tarfile

import numpy as np
import pandas as pd
import astropy.time as atime
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

from configuration import SATELLITE, SAT_NAME, SAVE_DIR, DATA_TYPES, GAP_THRESHOLD


LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style='{',
    format='{levelname}: {name} ({funcName}) [{lineno}]:  {message}'
)
logger = logging.getLogger(__name__)


def _uncompress_files(tgz_file: pathlib.Path) -> None:
    """Safely uncompress file in its directory."""
    with tarfile.open(tgz_file, 'r') as tgz:
        members = tgz.getmembers()
        for member in members:
            if member.name.endswith(".DBL"):
                try:
                    tgz.extract(member, path=SAVE_DIR, filter='data')
                    logger.info(f"Extracting file {member.name}.")
                except tarfile.FilterError:
                    logger.error(f"Error extracting file {member.name}. Check archive {tgz_file}.")
                    raise

def _read_single_file(qfile: pathlib.Path) -> pd.DataFrame:
    """Read a single quaternion file to a pandas DataFrame."""
    # default arguments
    kwargs = {
        # 'delim_whitespace': True,
        'sep': '\s+',
        'comment': '#',
        'header': None,
    }

    logger.info(f"Reading file {qfile}.")
    # set useful columns
    match SATELLITE:
        case 'ja3':
            try:
                sv_args = {
                    'usecols': [0, 1, 3, 6, 9, 12],
                    'names': ['_date', '_time'] + [f'q{i}' for i in range(4)],
                }
                df = pd.read_csv(qfile, **kwargs, **sv_args)
            except pd.errors.ParserError:  # it's a 'qsolp' file
                sv_args = {
                    'usecols': [0, 1, 3, 6],
                    'names': ['_date', '_time', 'left_panel', 'right_panel'],
                }
                df = pd.read_csv(qfile, **kwargs, **sv_args)
        case 's3a' | 's3b' | 's6a':
            sv_args = {
                'usecols': [0, 1, 2, 3, 4, 5],
                'names': ['_date', '_time'] + [f'q{i}' for i in range(4)],
            }
            df = pd.read_csv(qfile, **kwargs, **sv_args)

    # parse date & time
    date_col = df.iloc[:, 0]
    time_col = df.iloc[:, 1]
    df['date_time'] = pd.to_datetime(date_col + ' ' + time_col, format='%Y/%m/%d %H:%M:%S.%f')
    # df.set_index('date_time', inplace=True)

    return df.drop(columns=['_date', '_time'])

def _fix_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Change the time scale and format of the DataFrame.
    Input is np.datetime64 in UTC (Jason) or GPST (Sentinel).
    Output is MJD (float) in TT.
    """
    logger.info("Fixing time scale.")
    # get time info from df
    time_ = df['date_time'].to_numpy()
    # change time scale to TT
    match SATELLITE:
        case 'ja3':
            # Jason quaternions are given at UTC times
            tt = atime.Time(time_, scale='utc').tt
        case 's3a' | 's3b' | 's6a':
            # Sentinel quaternions are given at GPST times, which is TAI
            tt = atime.Time(time_, scale='tai').tt
    # replace date_time with new time scale
    df['date_time'] = tt.to_value(format='datetime64')
    logger.debug(df)

    # set date_time as index
    return df.set_index('date_time')

def _interpolate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute scipy.spatial.transform.Rotation objects from quaternions and
    interpolate at 1 sec interval using scipy.spatial.transform.Slerp.

    For Jason satellites, also interpolate (linearly) solar panel angles.
    """
    # get times
    times = df.index.values
    logger.debug(times)

    # do we need to interpolate?
    # usually, Sentinel files are already indexed at 1s intervals
    if SAT_NAME.startswith('Sentinel'):
        # first difference of indices in s
        dt = np.diff(times) / np.timedelta64(1, 's')
        if np.max(dt) < GAP_THRESHOLD:
            logger.info(f"Skipping interpolation; no data gaps exceeding {GAP_THRESHOLD}s found.")
            return df

    # compute rotations
    rotations = df.loc[:, ['q0', 'q1', 'q2', 'q3']].to_numpy()
    rotations = R.concatenate(
        [R.from_quat(q, scalar_first=True) for q in rotations]
    )
    logger.debug(rotations)

    # create Slerp object
    times_ = atime.Time(times, scale='tt').mjd
    slerp = Slerp(times_, rotations)

    # construct time array at constant intervals of 1 sec for one day
    mjd = np.floor(times_.mean())
    times = np.arange(start=mjd, stop=mjd + 1, step=1. / 86400.)

    # interpolate
    logger.info("Interpolating quaternions.")
    rotations = slerp(times)

    # Jason satellite; interpolate solar panel angles
    if SATELLITE == 'ja3':
        logger.info("Interpolating solar panel angles.")

        # TODO: FIX THIS HACK!
        # Make it work with np.datetime64 indices!
        df.index = times_

        df_ = df[['left_panel',
                  'right_panel']].reindex(df.index.union(times)).interpolate(method='polynomial',
                                                                             order=1)
        df_ = df_[~df_.index.isin(df.index.difference(times))]
        df_.index = atime.Time(df_.index.to_numpy(),
                               format='mjd', scale='tt').to_value(format='datetime64')
        logger.debug(df_.shape, df_.columns, df_.index)

    # construct the new DataFrame
    df = pd.DataFrame(
        data=rotations.as_quat(scalar_first=True),
        index=times,
        columns=[f'q{i}' for i in range(4)]
    )
    logger.debug(df.shape, df.columns, df.index)

    # fix index
    df.index = atime.Time(df.index.to_numpy(),
                          format='mjd', scale='tt').to_value(format='datetime64')

    # Jason satellite; merge
    if SATELLITE == 'ja3':
        df = pd.merge(df, df_, left_index=True, right_index=True)

    return df

def _process_single_file(qfile: pathlib.Path, solp_file: pathlib.Path = None) -> pd.DataFrame:
    """Process a single quaternion file, or a pair (body -- panels) in case of Jason satellite."""
    # read "body" q-file
    df = _read_single_file(qfile)

    # Jason satellite; read and merge "panels" file
    if solp_file is not None:
        df_ = _read_single_file(solp_file)
        df = pd.merge(df, df_, how='left', on='date_time').sort_values('date_time')

    # fix time scale
    df = _fix_time(df)

    # interpolate at regular intervals
    df = _interpolate(df)

    # convert time format
    df.index = atime.Time(df.index.values, scale='tt').mjd

    return df

def _process_jason_files(data_path: str = SAVE_DIR) -> pd.DataFrame:
    """Walk through the given directory, read, process and concatenate quaternion files."""
    # construct qbody and qsolp file pairs
    qfiles = list(zip(
        sorted(list(pathlib.Path(data_path).glob(f'*{DATA_TYPES[0]}*'))),
        sorted(list(pathlib.Path(data_path).glob(f'*{DATA_TYPES[1]}*')))
    ))

    # process the file pairs
    dfs = []
    for q in qfiles:
        dfs.append(_process_single_file(*q))

    # concatenate to a single pandas DataFrame
    return pd.concat(dfs)

def _process_sentinel_files(data_path: str = SAVE_DIR) -> pd.DataFrame:
    """Walk through the given directory, read, process and concatenate quaternion files."""
    # extract the DBL files
    for tgz_file in pathlib.Path(data_path).glob(f'{SATELLITE.upper()}_OPER_AUX_PROQUA_POD_*'):
        _uncompress_files(tgz_file)

    # process each file
    dfs = []
    for qfile in pathlib.Path(data_path).glob('*.DBL'):
        dfs.append(_process_single_file(qfile))

    # delete DBL files
    for dbl_file in pathlib.Path(data_path).glob('*.DBL'):
        dbl_file.unlink(missing_ok=True)

    # concatenate to a single pandas DataFrame
    return pd.concat(dfs)

def _serialize(df: pd.DataFrame) -> None:
    """Serialize the concatenated quaternion data to pickle."""
    df.to_pickle(pathlib.Path(SAVE_DIR, f'qua_{SATELLITE}.pkl'))

def _deserialize() -> pd.DataFrame:
    """Read a pandas DataFrame from a pickle file."""
    return pd.read_pickle(pathlib.Path(SAVE_DIR, f"qua_{SATELLITE}.pkl"))

def preprocess() -> None:
    """Process quaternion files and create CSV files."""
    logger.info(f"Processing {SAT_NAME} quaternion files.")
    match SATELLITE:
        case 'ja3':
            df = _process_jason_files()
        case 's3a' | 's3b' | 's6a':
            df = _process_sentinel_files()

    # output
    csv_file = f'{SAVE_DIR}/qua_{SATELLITE}.csv'
    logger.info(f"Quaternions file is saved to {csv_file}.")
    df.to_csv(csv_file, sep=" ", float_format="%0.9f", header=False)


if __name__ == '__main__':
    preprocess()
