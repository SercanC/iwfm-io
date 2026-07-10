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
import tempfile
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
    tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    try:
        _fetch(url, tmp_zip, show_progress)

        digest = _sha256(tmp_zip)
        expected = KNOWN_DLLS[version]
        if digest != expected:
            raise RuntimeError(
                f"Downloaded archive failed its integrity check "
                f"(sha256 {digest} != expected {expected}). "
                "Not installing.")

        with zipfile.ZipFile(tmp_zip) as zf:
            names = [n for n in zf.namelist()
                     if n.lower().endswith("iwfm_c_x64.dll")]
            if not names:
                raise RuntimeError("Archive does not contain IWFM_C_x64.dll")
            with zf.open(names[0]) as src, open(dll_path, "wb") as out:
                out.write(src.read())
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass

    if show_progress:
        print(f"Installed: {dll_path}")
        print(f'Use it with iwfm_io.dll.load_dll(version="{version}") or '
              f'IWFMModel(..., dll_version="{version}").')
    return dll_path


def _fetch(url, dest, show_progress):
    """Download *url* to *dest* with a simple progress line."""
    def _hook(blocks, block_size, total):
        if not show_progress or total <= 0:
            return
        done = min(blocks * block_size, total)
        pct = 100.0 * done / total
        print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB ({pct:3.0f}%)",
              end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=_hook)
    if show_progress:
        print()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
