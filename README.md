# attitude: Preprocess attitude files


<!-- ## Introduction -->
This project prepares satellite attitude files to be used in Precise Orbit Determination (POD). 
Currently, it uses quaternions and produces attitude files that span a full (GPS)
week<sup>[1](#myfootnote1)</sup> that contains a given date.


## Installation
The easiest way to install the package is using [uv](https://github.com/astral-sh/uv). 
After downloading, you simply have to run 
`uv sync` 
and you're good to go.

Alternatively, you can use [pip](https://pypi.org/project/pip/) to install the project, via 
`pip install .` (or `pip install -e .` for an editable version).


## Usage
~~After editing the configuration file [`configuration.py`](src/configuration.py), the basic usage is
straightfowrward: \
`python attitude.py <date>` \
eg. `python attitude.py 2021-12-17` will produce the attitude file for the (extended) week that
contains this date (2021-12-10 to 2021-12-19).~~
After installation, you'll have an executable named `prepattitude` in your PATH. The program contains 
a help message, triggered with `-h` or `--help`. Basic usage includes adding a satellite name/id and 
the date of interest, e.g. `prepattitude -e 2021-12-17 -s s3b`. This command will produce the attitude 
file for the (extended) week that contains this date (2021-12-10 to 2021-12-19).

### Note for CDDIS Web Archive
For some satellites quaternion files are archived and downloaded from [CDDIS](https://cddis.nasa.gov/) 
(e.g. JASON[123] missions). To download these you will need a [.netrc](https://cddis.nasa.gov/Data_and_Derived_Products/CreateNetrcFile.html) 
file.

### Note for Copernicus Web Archive
For some satellites quaternion files are archived and downloaded from [Copernicus](https://dataspace.copernicus.eu/) 
(e.g. Sentinel missions). To download these you will need a [.s3cfg](https://documentation.dataspace.copernicus.eu/APIs/S3.html) 
file, placed at the user's home directory.

## Output
The output file is a space delimited tabular file.  The columns depend on the satellite "family".

  - `MJDay` is Modified Julian day (integer),
  - `SoD` are the seconds of day, i.e. seconds passed since the start of `MJDay` (fractional),
  - `Q0` is the real part of the quaternion,
  - `Q1`, `Q2`, `Q3` are the imaginary parts,
  - `LP` and `RP` are the rotation angles of the left and right panel, respectively (Jason
    satellites.)

## Available Satellites:

  Satellite Id| Name      |Launch Yr| Archive
  ------------|-----------|---------|--------
  `ja3`       |Jason-3    |2016     |[CDDIS](https://cddis.nasa.gov/archive/doris/ancillary/quaternions/ja3)
  `s3a`       |Sentinel-3A|2016     |[Copernicus](https://dataspace.copernicus.eu/)
  `s3b`       |Sentinel-3B|2018     |[Copernicus](https://dataspace.copernicus.eu/)
  `s6a`       |Sentinel-6A|2020     |[Copernicus](https://dataspace.copernicus.eu/)

#### Jason satellites
`MJDay SoD Q0 Q1 Q2 Q3 LP RP`


#### Sentinel satellites
`MJDay SoD Q0 Q1 Q2 Q3`

### Caveat (Fixed)
~~If the "working" directory is not empty, the software will concatenate ALL available quaternion
files, even the ones not downloaded in the current 'run'.~~


<!-- ## Contributing
Provide guidelines for contributing to your project. -->


## License
Licensed under the MIT License.  See [LICENSE](LICENSE).



---
<a name="myfootnote1">1</a>  Actually, the GPS week is extended by one day both before and after,
ie. it contains 9 days (Saturday to Monday), in order to be useful in computing arcs around Sundays
and Saturdays.
