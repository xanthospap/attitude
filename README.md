# Product Download & Preprocessing Facilities for DORIS

## Installation

Affter cloning, you can use `pip` to install the package, e.g.
`pip install .` or `pip install -e .` for an editable version. Pick the latter 
if you need to edit the source code.

## Products, Data and Executables

| Product Type   | Program                          | Notes        |
| ------------   | -------------------------------  | -------------|
| attitude files | `prepattitude`                   | Download and pre-process satellite-specific (measured) attitude files |
| RINEX (data)   | `rnxdwn`                         | Download DORIS RINEX files |
| orbits         | `sp3dwn`                         | Download (final) satellite-specific `sp3c` file(s) |
| VMF            | `vmfdwn`                         | Download [VMF](https://vmf.geo.tuwien.ac.at/) product files. For now, we only handle gridded `V3GR` VMF3-specific files |
| satellite mass | `satmass`                        | Download satellite-specific mass history files |

Information on the data/products can be found in [products](docs/products.md). The `Program` 
column above lists the programs available system-wide once you install the project.

## Usage

For usage type any program name followed by `-h` or `--help`. 

## Credentials

### Note for CDDIS Web Archive
For some satellites quaternion files are archived and downloaded from [CDDIS](https://cddis.nasa.gov/) 
(e.g. JASON[123] missions). To download these you will need a [.netrc](https://cddis.nasa.gov/Data_and_Derived_Products/CreateNetrcFile.html) 
file.

### Note for Copernicus Web Archive
For some satellites quaternion files are archived and downloaded from [Copernicus](https://dataspace.copernicus.eu/) 
(e.g. Sentinel missions). To download these you will need a [.s3cfg](https://documentation.dataspace.copernicus.eu/APIs/S3.html) 
file, placed at the user's home directory.

## Data & Products not Listed Here

### Space-Weather Data

Space-weather data can be downloaded from [CelesTrak](https://celestrak.org/SpaceData/) in `csv` format (do not try 
downloading the older `legacy` format, use the current standard).

### Earth Orientation Parameters

These data files can be downloaded from [IERS](https://hpiers.obspm.fr/iers/eop/), using either the `C04/14` or the `C04/20` series. A quick link to the latest file is 
[https://hpiers.obspm.fr/iers/eop/eopc04_20_v3/eopc04.1962-now](https://hpiers.obspm.fr/iers/eop/eopc04_20_v3/eopc04.1962-now)

## Attitude Download & Pre-Processing

The output file is a space delimited tabular file.  The columns depend on the satellite "family". Note that 
the output file contains date/time information in the **TT timescale** (regardless of satellite or input file(s)).

  - `MJDay` is Modified Julian day (integer) in TT,
  - `SoD` are the seconds of day, i.e. seconds passed since the start of `MJDay` (fractional) in TT,
  - `Q0` is the real part of the quaternion,
  - `Q1`, `Q2`, `Q3` are the imaginary parts,
  - `LP` and `RP` are the rotation angles of the left and right panel, respectively (Jason
    satellites.)

### Available Satellites:

  | Satellite Id | Name        | Launch Yr | Archive                                                                 |
  | ------------ | ----------- | --------- | ----------------------------------------------------------------------- |
  | `ja3`        | Jason-3     | 2016      | [CDDIS](https://cddis.nasa.gov/archive/doris/ancillary/quaternions/ja3) |
  | `s3a`        | Sentinel-3A | 2016      | [Copernicus](https://dataspace.copernicus.eu/)                          |
  | `s3b`        | Sentinel-3B | 2018      | [Copernicus](https://dataspace.copernicus.eu/)                          |
  | `s6a`        | Sentinel-6A | 2020      | [Copernicus](https://dataspace.copernicus.eu/)                          |

#### Jason satellites
`MJDay SoD Q0 Q1 Q2 Q3 LP RP`


#### Sentinel satellites
`MJDay SoD Q0 Q1 Q2 Q3`

## License
Licensed under the MIT License.  See [LICENSE](LICENSE).
