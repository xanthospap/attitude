import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt


# defaultPlotOptions = {
#    "style_sheet": "default",
#    "data_points_color": "blue",
#    "data_points_line_width": 1.2,
#    "line_color": "blue",
#    "line_style": "--",
#    "error_bar_color": (1.0, 0.3, 0.3, 0.3),
# }


MJD_MINUS_CNESJD = 33282e0


def datetime_from_mjd_and_sod(mjd, sod):
    mjd_epoch = datetime(1858, 11, 17, 0, 0, 0)
    return mjd_epoch + timedelta(days=mjd, seconds=sod)


def parse_cness_mass(
    fn: str,
    start: datetime = datetime.min,
    stop: datetime = datetime.max,
):
    result = {"data": []}
    with open(fn, "r") as fin:
        for line in fin.readlines():
            if line.startswith("C"):
                if "SATELLITE" in line:
                    # C*                    *** SATELLITE SENT3B ***
                    result["sat"] = line.split()[-2]
                elif "nitial mass (kg)" in line:
                    # C* Initial mass (kg) :  1130.000
                    result["mass_init"] = float(line.split()[-1])
                elif "nitial center of gravity (m)" in line:
                    # C* Initial center of gravity (m) : Xinit= +1.4888, Yinit= +0.2174, Zinit= +0.0094
                    l = line.split()
                    r0 = [float(x.rstrip(",")) for x in [l[8], l[10], l[12]]]
                    result["cog_init"] = np.array(r0)
            elif line.startswith(
                "/-----/---------/---------/---------/---------/---------/"
            ):
                pass
            else:
                l = line.split()
                mjd = int(l[0]) + 33282e0
                t = datetime_from_mjd_and_sod(mjd, float(l[1]))
                dmass, dx, dy, dz = [float(l[i]) for i in range(2, 6)]
                dcog = np.array([dx, dy, dz])
                if t >= start and t < stop:
                    result["data"].append((t, dmass, dcog))
    return result


def plot_dmdg_variations(data, plotOptions=None):
    fig, ax = plt.subplots(2, 1, sharex=True)
    # ax.set_title(f"Satellite {data['sat']}")
    x = [t[0] for t in data["data"]]
    dm = [t[1] for t in data["data"]]
    dr = [t[2] for t in data["data"]]
    # 1. Scatter plot
    ax[0].scatter(
        x,
        dm,
        zorder=3,
    )
    # 2. Line plot connecting the points
    ax[0].plot(
        x,
        dm,
        zorder=1,
    )
    ax[0].set_xlabel("Time")
    ax[0].set_ylabel("Mass Variations [kg]")
    ax[0].grid(True)
    for i, l in zip([0, 1, 2], ["dX", "dY", "dZ"]):
        ax[1].scatter(x, [ar[i] for ar in dr], zorder=3, label=l)
        ax[1].plot(x, [ar[i] for ar in dr], zorder=1, label="_nolegend_")
    ax[0].set_xlabel("Time")
    ax[0].set_ylabel("Mass Variations [kg]")
    ax[1].set_ylabel("CoG Variations [m]")
    ax[1].legend()
    ax[0].grid(True)
    ax[1].grid(True)
    return fig, ax
    # pdf.savefig(fig)
    # plt.close(fig)
    # plt.show()
