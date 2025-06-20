# -*- coding: utf-8 -*-

import datetime
import logging
import pathlib
import re
from os.path import exists, basename

from prepattitude.configuration import SATELLITE_INFO

def ja_product_range(satellite, fn, logger):
    fn = basename(fn.strip())
    if f"{satellite}qsolp" in fn:
        match = re.match(r"ja[123]qsolp(\d{14})_(\d{14})\.\d{3}", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
        else:
            RuntimeError(f'Failed to find product range for file {fn}; matching failed.')
    elif f"{satellite}qbody" in fn:
        match = re.match(r"ja[123]qbody(\d{14})_(\d{14})\.\d{3}", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
        else:
            RuntimeError(f'Failed to find product range for file {fn}; matching failed.')
    else:
        logger.debug("Failed matching product name for (remote) filenamei {f}; skipped.")
        return datetime.datetime.min, datetime.datetime.min
        # raise RuntimeError(f'Failed to find product range for file {fn}; expected {satellite}qsolp* or {satellite}qbody*')
