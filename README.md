# DORIS/POD Product Preparation

This package downloads and, where needed, decompresses the external products
used by `dpod`.  It provides small product-specific commands and the `prepyda`
orchestrator, which reads paths and the processing interval from a dpod YAML
configuration.

## Installation

```bash
python -m pip install .
```

Use `python -m pip install -e .` for an editable development installation.

## Commands

| Command | Product |
| --- | --- |
| `rnxdwn` | Daily DORIS RINEX observations from IGN |
| `dpoddwn` | DPOD SINEX and frequency-correction files from IGN |
| `vmfdwn` | VMF3 V3GR grids and ellipsoidal orography |
| `eopdwn` | IERS C04 Earth-orientation parameters |
| `aod1bdwn` | AOD1B RL06/RL07 dealiasing or RL06 atmospheric tides |
| `swdwn` | CelesTrak `SW-Last5Years.csv` |
| `satmass` | IDS/CNES satellite mass history |
| `satmandwn` | IDS/CNES satellite maneuver history |
| `sp3dwn` | Satellite-specific reference SP3 orbits |
| `prepattitude` | Download and preprocess measured attitude products |
| `prepyda` | Prepare every applicable product configured in a dpod YAML file |

SP3 downloading is deliberately standalone.  A dpod YAML file does not specify
the reference-orbit archive, analysis center, version, or input SP3 filename;
therefore `prepyda` does not attempt to choose one.

Every command documents its complete interface through `--help`.

## All-in-one preparation

```bash
prepyda app/dpod.yaml
```

Relative paths in the YAML are resolved below the current working directory,
not below the directory containing the YAML file.  A different root can be
selected explicitly:

```bash
prepyda app/dpod.yaml --root-dir=/home/user/foo/bar
```

With this command and the YAML value:

```yaml
eop: data/eopc04.1962-now
```

the target is:

```text
/home/user/foo/bar/data/eopc04.1962-now
```

`--products` restricts preparation to named product families:

```bash
prepyda app/dpod.yaml --products rinex vmf3 eop
```

The available names are printed by `prepyda --help`.  Unknown names are
rejected by the command-line parser.  With `--products all`, a handler acts
only when the corresponding YAML field exists and is applicable; unrelated
YAML sections are ignored.

The YAML parser intentionally does not enforce the complete dpod schema.  It
does reject duplicate YAML keys, duplicate satellite entries, and unknown
satellite identifiers because these are ambiguous and likely mistakes.

## UTC and temporal coverage

All user-supplied epochs are UTC.  A datetime without a timezone is interpreted
as UTC.  A datetime with `Z` or an explicit offset is converted to UTC before
archive filenames and coverage intervals are computed.

Products that need temporal coverage include surrounding records:

- VMF3 includes `floor(start, 6 h)` through `ceil(stop, 6 h)`;
- AOD1B includes a three-hour margin on both sides of the processing interval;
- attitude preparation uses a 30-minute margin on both sides.

## Attitude preprocessing and sampling

Attitude preprocessing preserves native source epochs by default.  ESA/IDS/CNES
quaternion records are therefore not resampled merely to obtain an evenly
spaced file.  Uneven source sampling is valid input for OrbitCommons.

Before writing, attitude records are stable-sorted by epoch and exact duplicate
epochs are removed; for overlaps, the later input occurrence is kept.  The
final file is checked to guarantee unique, strictly increasing epochs.
Quaternion records are never arithmetic-averaged during duplicate removal.

For satellites whose products contain separate body-quaternion and solar-panel
streams (currently Jason and SWOT), native mode keeps the **union** of the raw
epochs from both streams.  At an epoch present in only one stream, the existing
raw component is kept unchanged and only the missing component is interpolated:
body quaternions use SLERP and panel angles use linear interpolation.  These
component interpolations are logged.  Thus the two source streams do not need
any exact timestamp matches.  If one stream does not temporally bracket an
unmatched epoch from the other stream, preprocessing fails rather than silently
dropping that raw epoch or extrapolating attitude.

For example, this keeps native CryoSat-2 quaternion epochs:

```bash
prepattitude --begin 2024-01-05 --end 2024-01-07 --satellite cs2 \
  --save-dir data
```

Uniform resampling is opt-in and is controlled only from the command line.
Supplying `--every-sec` to either `prepattitude` or `prepyda` requests a regular
output grid; all required attitude components are interpolated onto that grid:

```bash
prepattitude --begin 2024-01-05 --end 2024-01-07 --satellite cs2 \
  --save-dir data --every-sec 5

prepyda app/dpod.yaml --every-sec 5
```

There is deliberately no `every_sec`/`nsec` attitude-sampling field in the dpod
YAML configuration.  Omitting the command-line option always means native
sampling.

## Existing files, compression, and missing products

Before downloading, the software always searches for both the requested path
and common compressed/uncompressed variants.  A local file is reusable only if
it exists, is a regular file, and is nonempty.  This is intentionally the only
general validation because the products have heterogeneous formats.

Decompression is enabled by default.  The following single-file compression
types are supported:

- gzip (`.gz`);
- bzip2 (`.bz2`);
- xz (`.xz`);
- Unix compress (`.Z`, using `gzip` or `uncompress`);
- ZIP containing exactly one regular file.

Compressed inputs are retained.  Use `--no-decompress` to keep only the
downloaded representation.  `--overwrite` refreshes products even if a
nonempty local variant is present.

A missing online file does not abort a preparation campaign.  It produces a
warning, is listed as missing in `downloads.json`, and preparation continues.
Invalid user configuration remains an immediate error.

EOP and space-weather files are continuously updated.  Existing copies are
scanned only for their first/last dates; if they do not cover the requested
UTC interval, they are downloaded again.  Prepared attitude files are treated
similarly using their first two numeric columns (`MJD(TT)` and seconds of day).

## YAML fields consumed by `prepyda`

The orchestrator currently recognizes only the fields needed to locate these
products:

```yaml
a-priori-coordinates:
  sinex: data/dpod2020_060.snx
  dpod_frequency_cor: data/dpod2020_060_freq_corr.txt

rinex:
  from: 2024-01-05 00:00:00
  to: 2024-01-06 12:00:00
  data_dir: data

troposphere:
  model: VMF3
  data_dir: data
  grid: 5x5

eop: data/eopc04.1962-now

dealiasing:
  model: AOD1B RL06
  data-dir: data

atmospheric-tide:
  model: AOD1B RL06
  data_dir: data/aod1b_tides
  tide_atlas_from_aod1b:
    k1: AOD1B_ATM_K1_06.asc
    m2: AOD1B_ATM_M2_06.asc

space-weather-data:
  celestrak_csv: data/SW-Last5Years.csv

satellite-attitude:
  - satellite: cs2
    cnes_sat_file: data/cs2mass.txt
    cnes_maneuver: data/cs2man.txt
    data_file: data/qua_cs2.csv
```

Files downloaded for scalar YAML fields are written with exactly the filename
specified by the YAML after decompression.  Rename operations are logged.

AOD1B dealiasing supports RL06 and RL07.  AOD1B atmospheric-tide files support
RL06 only; requesting RL07 atmospheric tides is an immediate error until that
product and its phase conventions are supported by dpod.

## Data sources

- DORIS RINEX and DPOD: IGN DORIS archive;
- mass and maneuver histories: IDS/CNES satellite repository;
- VMF3: TU Wien VMF data service;
- EOP: IERS Earth Orientation Centre C04 series;
- AOD1B: GFZ ISDC HTTPS archive;
- space weather: CelesTrak;
- reference SP3: IGN or authenticated CDDIS archive;
- attitude: CDDIS, Copernicus Data Space, or CryoSat PDS depending on mission.

CDDIS products require Earthdata credentials configured for `requests`, often
through `.netrc`.  Copernicus attitude products normally require an S3
configuration.  CryoSat attitude products require `CRYOSAT_FTP_USER` and
`CRYOSAT_FTP_PASSWORD`, or the corresponding `prepyda` command-line options.

## Manifest and exit behavior

`prepyda` writes `downloads.json` below `--root-dir` by default.  It records
available paths, unavailable items, warnings, and completeness per product.
Missing remote products do not change the successful exit status.  Invalid
YAML/configuration and local programming errors do.

## License

Licensed under the MIT License.
