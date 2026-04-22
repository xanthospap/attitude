# DATA & PRODUCTS

- `YYYY` = 4-digit year, e.g. 2026
- `YY`   = 2-digit year, e.g. 26
- `MM`   = 20digit month, e.g. 02
- `DDD`  = 3-digit day of year, in range [1, 365/366]
- `DD`   = 2-digit day of month
- `SSS`  = 3-digit satellite specifier
- `CCC`  = 3-character analysis center name, e.g.

    - grg	Centre national d'études spatiales (CNES)/Space Geodesy Research Group (GRGS)
    - gsc	NASA Goddard Space Flight Center
    - lca	Laboratoire d’Etudes en Géophysique et Océanographie Spatiales-Collecte Localisation Satellites (LEGOS-CLS)
    - ssa	Segment Sol Multimission Altimetry and Orbitography (SSALTO)

Info can be found in the [IDS relevant site](https://ids-doris.org/data-products/tables-of-data-products.html).

## DORIS RINEX

- Format: [RINEX DORIS 3.0](https://ids-doris.org/documents/BC/data/RINEX_DORIS.pdf)
- Naming convention: `SSSrxYYDDD.001.Z`
- Validity: 1 day

### CDDIS

- data archive: [https://cddis.nasa.gov/archive/doris/data/](https://cddis.nasa.gov/archive/doris/data/)
- credentials: needed!!
- format: `SSS/YYYY/SSSrxYYDDD.001.Z`, example `https://cddis.nasa.gov/archive/doris/data/ja3/2026/ja3rx26104.001.Z`

### IGN

- data archive: [ftp://doris.ign.fr/pub/doris/data/](ftp://doris.ign.fr/pub/doris/data/)
- credentials: none (anonymous login, mail as password)
- format: `/pub/doris/data/SSS/YYYY/SSSrxYYDDD.001.Z`, example `/pub/doris/data/ja3/2026/ja3rx26104.001.Z`

## ORBITS (sp3)

- Format: [sp3c](https://files.igs.org/pub/data/format/sp3c.txt)
- Naming convention: `CCC/SSS/CCCSSSVV.bXXDDD.eYYEEE.dgs.sp3.LLL.Z`
- Validity: depends ...
- see [CDDIS DORIS product page](https://www.earthdata.nasa.gov/data/space-geodesy-techniques/doris/international-doris-service-orbit-product)

### CDDIS 

- data archive: [https://cddis.nasa.gov/archive/doris/products/orbits/](https://cddis.nasa.gov/archive/doris/products/orbits/)
- credentials: needed!!
- format: see above, example `https://cddis.nasa.gov/archive/doris/products/orbits/ssa/ja3/ssaja320.b16147.e16157.DG_.sp3.001.Z`

## IGN

- data archive: [ftp://doris.ign.fr/pub/doris/products/orbits](ftp://doris.ign.fr/pub/doris/products/orbits)
- credentials: none (anonymous login, mail as password)
- format: see above, example `/pub/doris/products/orbits/ssa/ja3/ssaja320.b16147.e16157.DG_.sp3.001.Z`

## VMF Data Server

The [VMF Data Derver](https://vmf.geo.tuwien.ac.at/) holds data files & products for troposphere delays models relevant to all space geodetic techniques.

Data are in yearly directories and contain 6-hour specific files. To cover a full day, we need 5 such files (i.e. include first file of the next day). 
There are two grid options available for these files, either `1x1` or `5x5`, which are both handled. 
Our software uses the VMF3-specific grid files which can be accessed here: [https://vmf.geo.tuwien.ac.at/trop_products/GRID/1x1/V3GR/V3GR_OP/](https://vmf.geo.tuwien.ac.at/trop_products/GRID/1x1/V3GR/V3GR_OP/) or [https://vmf.geo.tuwien.ac.at/trop_products/GRID/5x5/V3GR/V3GR_OP/](https://vmf.geo.tuwien.ac.at/trop_products/GRID/5x5/V3GR/V3GR_OP/) for the `5x5` grid.
Based on the frid choice, one will also need the relevant `orography` file accessible here: [https://vmf.geo.tuwien.ac.at/station_coord_files/](https://vmf.geo.tuwien.ac.at/station_coord_files/). 

- data archive: [https://vmf.geo.tuwien.ac.at/trop_products/GRID/1x1/V3GR/V3GR_OP/](https://vmf.geo.tuwien.ac.at/trop_products/GRID/1x1/V3GR/V3GR_OP/) or [https://vmf.geo.tuwien.ac.at/trop_products/GRID/5x5/V3GR/V3GR_OP/](https://vmf.geo.tuwien.ac.at/trop_products/GRID/5x5/V3GR/V3GR_OP/)
- credentials: none 
- format: `V3GR_YYYYMMDD.H??`, with `??` a 6-hour interval in [`00`, `06`, `12`, `18`]; example `https://vmf.geo.tuwien.ac.at/trop_products/GRID/5x5/V3GR/V3GR_OP/2025/V3GR_20250101.H06`

