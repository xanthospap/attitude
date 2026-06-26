from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
from ftplib import FTP, FTP_TLS, all_errors
import logging
import os
from pathlib import Path
import socket
import ssl

from sources.attitude import dates_to_scan_for_range, product_overlaps_range


logger = logging.getLogger(__name__)


CRYOSAT_FTPS_HOST = "ftppds-hispeed.cryosat.esa.int"
CRYOSAT_FTPS_PORT = 990
CRYOSAT_AUX_PROQUA_BASE_PATH = "AUX_PROQUA"


class ImplicitFTP_TLS(FTP_TLS):
    """FTP_TLS variant for implicit FTPS servers on port 990.

    The CryoSat PDS FTPS endpoint uses implicit TLS.  Some FTPS servers
    additionally require the data connection used by LIST/NLST/RETR to reuse
    the TLS session from the control connection.  Python's FTP_TLS does not
    pass that session by default, while clients such as lftp usually do.
    """

    def connect(self, host: str = "", port: int = 0, timeout=None, source_address=None):
        if host:
            self.host = host
        if port > 0:
            self.port = port
        if timeout is not None:
            self.timeout = timeout
        if source_address is not None:
            self.source_address = source_address

        self.sock = socket.create_connection(
            (self.host, self.port),
            self.timeout,
            source_address=getattr(self, "source_address", None),
        )
        self.af = self.sock.family
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        """Open a protected data connection reusing the control TLS session."""

        conn, size = FTP.ntransfercmd(self, cmd, rest)

        if self._prot_p:
            session = getattr(self.sock, "session", None)
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=session,
            )

        return conn, size


@contextmanager
def open_cryosat_ftps(
    user: str | None = None,
    password: str | None = None,
    *,
    host: str = CRYOSAT_FTPS_HOST,
    port: int = CRYOSAT_FTPS_PORT,
    timeout: float = 60.0,
):
    """Open an authenticated CryoSat implicit-FTPS session."""

    user = user or os.getenv("CRYOSAT_FTP_USER")
    password = password or os.getenv("CRYOSAT_FTP_PASSWORD")

    if not user or password is None:
        raise ValueError(
            "CryoSat FTPS credentials are required. Provide user/password or set "
            "CRYOSAT_FTP_USER and CRYOSAT_FTP_PASSWORD."
        )

    context = ssl.create_default_context()
    ftp = ImplicitFTP_TLS(context=context, timeout=timeout)

    try:
        ftp.connect(host=host, port=port)
        ftp.login(user=user, passwd=password)
        ftp.prot_p()
        ftp.set_pasv(True)
        yield ftp
    finally:
        try:
            ftp.quit()
        except all_errors:
            try:
                ftp.close()
            except all_errors:
                pass


def _month_directory_candidates_for_range(
    start: dt.datetime,
    end: dt.datetime,
    base_path: str = CRYOSAT_AUX_PROQUA_BASE_PATH,
) -> list[list[str]]:
    months = sorted(
        {
            (date.year, date.month)
            for date in dates_to_scan_for_range(start=start, end=end, pad_days=1)
        }
    )

    candidates: list[list[str]] = []
    for year, month in months:
        month_candidates = [f"{base_path.strip('/')}/{year:04d}/{month:02d}"]

        # Some user-facing CryoSat archive examples show a five-digit year
        # directory such as 20024 for 2024.  Keep this as a fallback candidate,
        # while preferring the standard YYYY layout.
        legacy_year = f"20{year % 1000:03d}"
        legacy_directory = f"{base_path.strip('/')}/{legacy_year}/{month:02d}"
        if legacy_directory not in month_candidates:
            month_candidates.append(legacy_directory)

        candidates.append(month_candidates)

    return candidates


def _format_ftp_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if text:
        return text
    return repr(exc)


def _list_names(ftp: FTP_TLS, directory: str) -> list[str]:
    current = ftp.pwd()
    try:
        ftp.cwd(directory)

        try:
            return [Path(name).name for name, _facts in ftp.mlsd() if Path(name).name]
        except all_errors:
            return [Path(name).name for name in ftp.nlst() if Path(name).name]
    finally:
        ftp.cwd(current)


def find_attitude_paths(
    start: dt.datetime,
    end: dt.datetime,
    *,
    user: str | None = None,
    password: str | None = None,
    base_path: str = CRYOSAT_AUX_PROQUA_BASE_PATH,
    host: str = CRYOSAT_FTPS_HOST,
    port: int = CRYOSAT_FTPS_PORT,
) -> list[str]:
    """Find CryoSat-2 AUX_PROQUA archives overlapping [start, end)."""

    paths: list[str] = []

    with open_cryosat_ftps(user=user, password=password, host=host, port=port) as ftp:
        for directories in _month_directory_candidates_for_range(
            start,
            end,
            base_path=base_path,
        ):
            filenames: list[str] | None = None
            directory: str | None = None
            errors: list[str] = []

            for candidate_directory in directories:
                try:
                    filenames = _list_names(ftp, candidate_directory)
                    directory = candidate_directory
                    break
                except all_errors as exc:
                    errors.append(
                        f"{candidate_directory}: {_format_ftp_error(exc)}"
                    )

            if filenames is None or directory is None:
                logger.warning(
                    "Could not list CryoSat FTPS directory candidates: %s",
                    "; ".join(errors),
                )
                continue

            for filename in filenames:
                upper_name = filename.upper()

                if "AUX_PROQUA" not in upper_name:
                    continue
                if not upper_name.endswith((".TGZ", ".TAR.GZ", ".EEF", ".XML")):
                    continue
                if not product_overlaps_range(filename, start, end):
                    continue

                paths.append(f"{directory}/{filename}")

    return sorted(set(paths))


def download_path(
    remote_path: str,
    output_dir: str | Path,
    *,
    ftp: FTP_TLS,
    overwrite: bool = False,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / Path(remote_path).name
    if output_file.exists() and not overwrite:
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    with tmp_file.open("wb") as fout:
        ftp.retrbinary(f"RETR {remote_path}", fout.write)

    tmp_file.replace(output_file)
    return output_file


def download_attitude(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    output_dir: str | Path,
    base_path: str = CRYOSAT_AUX_PROQUA_BASE_PATH,
    overwrite: bool = False,
    user: str | None = None,
    password: str | None = None,
    host: str = CRYOSAT_FTPS_HOST,
    port: int = CRYOSAT_FTPS_PORT,
) -> list[Path]:
    """Download CryoSat-2 AUX_PROQUA archives overlapping [start, end)."""

    sat = satellite.lower()
    if sat not in {"cs2", "cryosat2", "cryosat-2"}:
        raise ValueError(f"Unsupported CryoSat attitude satellite: {satellite}")

    remote_paths = find_attitude_paths(
        start=start,
        end=end,
        user=user,
        password=password,
        base_path=base_path,
        host=host,
        port=port,
    )

    files: list[Path] = []

    with open_cryosat_ftps(user=user, password=password, host=host, port=port) as ftp:
        for remote_path in remote_paths:
            try:
                files.append(
                    download_path(
                        remote_path=remote_path,
                        output_dir=output_dir,
                        ftp=ftp,
                        overwrite=overwrite,
                    )
                )
            except all_errors as exc:
                logger.error(
                    "Failed to download CryoSat FTPS file %s: %s",
                    remote_path,
                    _format_ftp_error(exc),
                )

    return files
