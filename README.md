# attitude: Preprocess attitude files


<!-- ## Introduction -->
This project prepares satellite attitude files to be used in Precise Orbit Determination (POD). \
Currently, it uses quaternions and produces attitude files that span a full (GPS)
week<sup>[1](#myfootnote1)</sup> that contains a given date.


## Installation
The easiest way to install the package is using [uv](https://github.com/astral-sh/uv). \
After downloading, you simply have to run \
`uv sync` \
and you're good to go.


## Usage
After editing the configuration file [`configuration.py`](src/configuration.py), the basic usage is
straightfowrward: \
`python attitude.py <date>` \
eg. `python attitude.py 2021-12-17` will produce the attitude file for the (extended) week that
contains this date (2021-12-10 to 2021-12-19).


## Output
The output file is a space delimited tabular file.  The columns depend on the satellite "family".

  - `MJD` is Modified Julian date,
  - `Q0` is the real part of the quaternion,
  - `Q1`, `Q2`, `Q3` are the imaginary parts,
  - `LP` and `RP` are the rotation angles of the left and right panel, respectively (Jason
    satellites.)


#### Jason satellites

```
MJD Q0 Q1 Q2 Q3 LP RP
```

#### Sentinel satellites
```
MJD Q0 Q1 Q2 Q3
```

### Caveat
If the "working" directory is not empty, the software will concatenate ALL available quaternion
files, even the ones not downloaded in the current 'run'.


<!-- ## Contributing
Provide guidelines for contributing to your project. -->


## License
Licensed under the MIT License.  See [LICENSE](LICENSE).


---
<a name="myfootnote1">1</a>  Actually, the GPS week is extended by one day both before and after,
ie. it contains 9 days (Saturday to Monday), in order to be useful in computing arcs around Sundays
and Saturdays.
