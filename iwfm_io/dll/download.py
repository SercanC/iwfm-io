"""Download official IWFM DLL builds into the user DLL directory.

The IWFM C-DLL is Windows-only, GPLv2, version-sensitive, and ~37 MB —
so it is not bundled in the ``iwfm-io`` wheel. Instead, builds are
published (with their corresponding source, per GPL) as assets on the
project's GitHub releases under ``dll-<version>`` tags, and this module
fetches them into ``~/.iwfm/dlls/<version>/`` where :func:`iwfm_io.dll.load_dll`
already looks.

Usage::

    import iwfm_io
    iwfm_io.dll.download_dll("2025.0.1747")
    model = iwfm_io.dll.IWFMModel(..., dll_version="2025.0.1747")
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
import zipfile

_USER_DLLS = os.path.join(os.path.expanduser("~"), ".iwfm", "dlls")
_RELEASE_URL = ("https://github.com/SercanC/iwfm-io/releases/download/"
                "dll-{version}/IWFM_C_x64-{version}.zip")

#: Published DLL builds and the sha256 of their release zip.
#: All are official DWR builds from the CNRA Open Data release archive
#: (https://data.cnra.ca.gov/dataset/iwfm-integrated-water-flow-model),
#: repackaged unmodified. The 2015-line DLLs ship from DWR as
#: IWFM2015_C_x64.dll and are renamed to the canonical IWFM_C_x64.dll.
KNOWN_DLLS = {
    "2025.0.1747":
        "c59c2f2e6aac17fec2920e229db5924e858c2b648b18a2ca43c1fbae24709915",
    "2025.0.1688":
        "1158af91c32aa1b92a9f727aa926be498f202cadf6e4bdc74b64f0f201daeb41",
    "2024.2.1594":
        "dfa00a85fb2633335394b5add60a02a5d8210e985d6125432dec0bf04749750c",
    "2015.3.1443":
        "f699023cbcd2573e9dbf7b6c052259b309e04a32b4207ab895082652cadc4846",
    "2015.1.1273":
        "2469a359b9da0889e0e7dde60c9e26d749cae70ec3ba6f5e2d82ef54f9d3a85e",
    "2015.0.1403":
        "a25825fd35935782cbb97d5b50393e870424699ae3d66d92361c8e10fadc0176",
}

DEFAULT_VERSION = "2025.0.1747"


def download_dll(version=DEFAULT_VERSION, dest_dir=None, force=False,
                 show_progress=True):
    """Download an official IWFM DLL build to the user DLL directory.

    Parameters
    ----------
    version : str
        IWFM build version, e.g. ``"2025.0.1747"``. Published versions
        are listed in :data:`KNOWN_DLLS`.
    dest_dir : str or Path, optional
        Target directory. Defaults to ``~/.iwfm/dlls/<version>/``,
        which ``load_dll(version=...)`` searches automatically.
    force : bool
        Re-download even if the DLL is already present.
    show_progress : bool
        Print download progress to stdout.

    Returns
    -------
    str
        Path to the downloaded ``IWFM_C_x64.dll``.

    Raises
    ------
    ValueError
        If *version* has no published release asset.
    RuntimeError
        If the downloaded archive fails its sha256 check.

    Notes
    -----
    The archive is fetched to ``<dest_dir>/IWFM_C_x64-<version>.zip.part``.
    When a previous attempt was interrupted (network drop, Ctrl-C) that
    partial file is kept and the next call resumes it with an HTTP
    ``Range`` request, restarting from scratch only when the server does
    not honour the range. The sha256 check always covers the complete
    archive, and the DLL is extracted to a ``.part`` file that is moved
    into place atomically, so a truncated ``IWFM_C_x64.dll`` is never
    left behind.
    """
    if version not in KNOWN_DLLS:
        raise ValueError(
            f"No published DLL build for version {version!r}. "
            f"Available: {sorted(KNOWN_DLLS)}. Other builds can be placed "
            f"manually in ~/.iwfm/dlls/<version>/IWFM_C_x64.dll — the DLL "
            "ships with IWFM from the DWR website."
        )

    dest_dir = os.path.join(_USER_DLLS, version) if dest_dir is None \
        else str(dest_dir)
    dll_path = os.path.join(dest_dir, "IWFM_C_x64.dll")
    if os.path.isfile(dll_path) and not force:
        if show_progress:
            print(f"IWFM DLL {version} already installed: {dll_path}")
        return dll_path

    url = _RELEASE_URL.format(version=version)
    if show_progress:
        print(f"Downloading IWFM DLL {version} ...")
        print(f"  {url}")

    os.makedirs(dest_dir, exist_ok=True)
    zip_part = os.path.join(dest_dir, f"IWFM_C_x64-{version}.zip.part")
    # An interrupted fetch (network error, Ctrl-C) propagates and leaves
    # the partial archive behind for the next call to resume.
    _fetch(url, zip_part, show_progress)
    try:
        # From here on the archive is complete: whatever happens next
        # (bad hash, bad payload, success) it is disposed of -- a resumed
        # download that does not add up is worthless as a resume base.
        digest = _sha256(zip_part)
        expected = KNOWN_DLLS[version]
        if digest != expected:
            raise RuntimeError(
                f"Downloaded archive failed its integrity check "
                f"(sha256 {digest} != expected {expected}). "
                "Not installing.")

        with zipfile.ZipFile(zip_part) as zf:
            names = [n for n in zf.namelist()
                     if n.lower().endswith("iwfm_c_x64.dll")]
            if not names:
                raise RuntimeError("Archive does not contain IWFM_C_x64.dll")
            part = dll_path + ".part"
            with zf.open(names[0]) as src, open(part, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            try:
                _check_pe_image(part)
            except RuntimeError:
                os.remove(part)
                raise
            os.replace(part, dll_path)   # never leave a truncated DLL
    finally:
        try:
            os.remove(zip_part)
        except OSError:
            pass

    if show_progress:
        print(f"Installed: {dll_path}")
        print(f'Use it with iwfm_io.dll.load_dll(version="{version}") or '
              f'IWFMModel(..., dll_version="{version}").')
    return dll_path


def _fetch(url, dest, show_progress):
    """Download *url* to *dest*, resuming a partial *dest* when possible.

    An existing non-empty *dest* is treated as the head of an interrupted
    download: the request carries ``Range: bytes=<size>-`` and, when the
    server answers ``206 Partial Content``, the remainder is appended.
    A ``200`` answer (no range support, or the file changed) restarts
    the download from scratch; ``416`` (range not satisfiable — the
    partial file is already as long as the asset, or longer) discards
    it and restarts too.
    """
    existing = 0
    try:
        existing = os.path.getsize(dest)
    except OSError:
        pass

    headers = {"User-Agent": "iwfm-io"}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if existing > 0 and exc.code == 416:
            try:
                os.remove(dest)
            except OSError:
                pass
            return _fetch(url, dest, show_progress)
        raise

    with resp:
        status = getattr(resp, "status", None)
        if status is None:
            status = resp.getcode()
        resumed = existing > 0 and status == 206
        length = int(resp.headers.get("Content-Length") or 0)
        if resumed:
            total = existing + length
            content_range = resp.headers.get("Content-Range") or ""
            if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
                total = int(content_range.rsplit("/", 1)[1])
            done = existing
            mode = "ab"
            if show_progress:
                print(f"  resuming at {existing / 1e6:.1f} MB")
        else:
            total = length
            done = 0
            mode = "wb"
            if existing > 0 and show_progress:
                print("  server did not honour the resume request; "
                      "downloading from the start")
        with open(dest, mode) as out:
            block = 1 << 20
            while True:
                chunk = resp.read(block)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if show_progress and total > 0:
                    pct = 100.0 * min(done, total) / total
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB "
                          f"({pct:3.0f}%)", end="", flush=True)
    if show_progress:
        print()


def _check_pe_image(path):
    """The extracted file must be a Windows PE image (``MZ`` header +
    ``PE\\0\\0`` signature); anything else is not a DLL and is refused."""
    with open(path, "rb") as fh:
        head = fh.read(0x40)
        if len(head) < 0x40 or head[:2] != b"MZ":
            raise RuntimeError(
                f"{os.path.basename(path)} is not a Windows DLL (no MZ "
                "header) -- the archive payload is not an IWFM build")
        pe_off = int.from_bytes(head[0x3C:0x40], "little")
        fh.seek(pe_off)
        if fh.read(4) != b"PE\0\0":
            raise RuntimeError(
                f"{os.path.basename(path)} is not a Windows DLL (no PE "
                "signature) -- the archive payload is not an IWFM build")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
