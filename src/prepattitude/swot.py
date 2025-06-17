from datetime import datetime, timedelta
import logging
import pathlib
import re
from ftplib import FTP
import xml.etree.ElementTree as ET
import numpy as np
from prepattitude.configuration import SATELLITE_INFO

from os.path import join, isfile, basename

LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)


def swo_qsol_to_csv(xmlfn, sep="\t"):
    ## Solar Panel 1 on side +X
    sp1 = {}
    ## Solar Panel 2 on side -X
    sp2 = {}

    # Parse the XML file
    tree = ET.parse(xmlfn)  # Replace with your actual file path
    root = tree.getroot()
    # Navigate to <DATA> section
    data_section = root.find("DATA")
    if data_section is not None:
        data_list = data_section.find("DATA_LIST")
        if data_list is not None:
            for param in data_list.findall("PARAM"):
                mnemo = param.findtext("MNEMO")
                onboard_date = param.findtext("ONBOARD_DATE")
                ground_date = param.findtext("GROUND_DATE")
                eng_value = param.findtext("ENG_VALUE")
                monitoring_status = param.findtext("MONITORING_STATUS")
                significativity_status = param.findtext("SIGNIFICATIVITY_STATUS")

                ## resolve onboard time ISO 8601, UTC
                t = datetime.strptime(onboard_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                ## Angle Values are <ENG_VALUE>, integer value to be divided by
                ## 120 in order to obtain values in degrees. Transform to radians
                a = np.radians(float(eng_value) / 120.0)

                if mnemo == "OBSSD_AM_ZESTSMPOSPX":
                    sp1[t] = a + np.radians(0.2e0)
                elif mnemo == "OBSSD_AM_ZESTSMPOSMX":
                    sp2[t] = a + np.radians(-0.2e0)
        else:
            print("No DATA_LIST found in DATA section.")
    else:
        print("No DATA section found.")

    missing = 0
    with open(".temp.csv", "w") as fout:
        for t, v1 in sp1.items():
            try:
                v2 = sp2[t]
                formatted = (
                    t.strftime("%Y/%m/%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"
                )
                print(
                    f"{formatted}{sep}{v1:.12e}{sep}{v1:.12e}{sep}{999.9}{sep}{v2:.12e}{sep}{v2:.12e}",
                    file=fout,
                )
            except:
                missing += 1
    # percentage of missing sp2 values in final array
    if missing * 100 / len(sp2) > 10:
        raise RuntimeError("ERROR Too many non-simulataneous solar panel quaternions!")
    return ".temp.csv"


def swo_product_range(fn):
    fn = basename(fn)
    if fn.startswith("swoqsolp"):
        match = re.match(r"swoqsolp(\d{14})_(\d{14})\.\d{3}\.xml", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
    elif fn.startswith("swoqbody"):
        match = re.match(r"swoqbody(\d{14})_(\d{14})\.\d{3}", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
    return None
