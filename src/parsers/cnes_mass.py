from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


MJD_MINUS_CNESJD = 33282.0


def datetime_from_mjd_and_sod(mjd: float, sod: float) -> datetime:
    mjd_epoch = datetime(1858, 11, 17, 0, 0, 0)
    return mjd_epoch + timedelta(days=mjd, seconds=sod)


def parse_cnes_mass(
    filename: str | Path,
    start: datetime = datetime.min,
    stop: datetime = datetime.max,
) -> dict:
    """
    Parse a CNES satellite mass file.

    Returns a dictionary with keys:
      - sat
      - mass_init
      - cog_init
      - data

    data is a list of tuples:

        (datetime, delta_mass, (dx, dy, dz))
    """

    filename = Path(filename)

    result = {
        "data": [],
    }

    with filename.open("r") as fin:
        for line in fin:
            if line.startswith("C"):
                if "SATELLITE" in line:
                    # Example:
                    # C*                    *** SATELLITE SENT3B ***
                    result["sat"] = line.split()[-2]

                elif "nitial mass (kg)" in line:
                    # Example:
                    # C* Initial mass (kg) :  1130.000
                    result["mass_init"] = float(line.split()[-1])

                elif "nitial center of gravity (m)" in line:
                    # Example:
                    # C* Initial center of gravity (m) :
                    # Xinit= +1.4888, Yinit= +0.2174, Zinit= +0.0094
                    fields = line.split()
                    result["cog_init"] = (
                        float(fields[8].rstrip(",")),
                        float(fields[10].rstrip(",")),
                        float(fields[12]),
                    )

                continue

            if line.startswith("/-----/"):
                continue

            fields = line.split()

            cnes_jd = int(fields[0])
            sod = float(fields[1])

            mjd = cnes_jd + MJD_MINUS_CNESJD
            epoch = datetime_from_mjd_and_sod(mjd, sod)

            if start <= epoch < stop:
                delta_mass = float(fields[2])
                delta_cog = (
                    float(fields[3]),
                    float(fields[4]),
                    float(fields[5]),
                )

                result["data"].append((epoch, delta_mass, delta_cog))

    return result
