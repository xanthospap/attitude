## Version 1.1
--------------

    * For the main program, the date is now parsed as `-d' or `--date'.
    * Full list of options added to main program as command line options. `configuration.py` now only contains basic config info.
    * Changed the executable name and definition(s) in the toml file.
    * All `download_data` functions/methods now return a list of (downloaded, i.e. local) files.
    * Output date (is csv fiels) is now written as MJDay (integral) and Seconds of Day (fractional).
    * Setup available with `pip`.
    * Drop dependencies on `arrow`, `jplephem`, `matplotlib`, `scipy`, `seaborn`.
