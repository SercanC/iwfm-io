"""DLL acquisition and resolution attacks (scripts a01, a20).

``download_dll`` runs against a mocked ``_fetch`` (a local zip is copied
into place — no network), with ``_USER_DLLS`` redirected into the test's
scratch folder so nothing lands in ``~/.iwfm``. ``load_dll`` resolution
is probed with traversal-shaped version strings and non-IWFM DLL paths.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import attempt, main, scratch_dir  # noqa: E402

FAKE_PAYLOAD = b"MZ not really a dll"


def _redirect_user_dlls(model_dir, tag="load"):
    """Point both modules' ``_USER_DLLS`` into a per-case scratch folder."""
    import iwfm_io.dll._dll as dd
    import iwfm_io.dll.download as dl
    user = scratch_dir(model_dir, f"dl_{tag}") / "userdlls"
    user.mkdir(parents=True, exist_ok=True)
    dd._USER_DLLS = str(user)
    dl._USER_DLLS = str(user)
    return user


def _workspace(model_dir, tag):
    """(scratch folder, user-DLL folder) private to one download case."""
    _redirect_user_dlls(model_dir, tag)
    return scratch_dir(model_dir, f"dl_{tag}")


def _make_zip(path, inner_name="IWFM_C_x64.dll", payload=FAKE_PAYLOAD):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(inner_name, payload)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mock_fetch(zip_path, raise_after=None):
    import iwfm_io.dll.download as dl

    def _fetch(url, dest, show_progress):
        shutil.copy2(zip_path, dest)
        if raise_after is not None:
            raise raise_after
    dl._fetch = _fetch


def _register(version, sha):
    import iwfm_io.dll.download as dl
    dl.KNOWN_DLLS[version] = sha


def _real_dll_bytes():
    from iwfm_io.dll import load_dll
    return Path(load_dll()._name).read_bytes()


def _dll_files(dest):
    dest = Path(dest)
    return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()) if dest.exists() else None


# -- download_dll -------------------------------------------------------------------

def case_dl_hash_mismatch(model_dir):
    """Wrong sha256 -> RuntimeError and NO DLL left in dest."""
    import iwfm_io.dll.download as dl
    t = _workspace(model_dir, "dl_hash_mismatch")
    z = t / "bad.zip"
    _make_zip(z)
    _mock_fetch(z)
    dest = t / "v_mismatch"

    def go():
        r = attempt(lambda: dl.download_dll("2025.0.1747", dest_dir=str(dest), show_progress=False))
        return {"call": r, "dest_files": _dll_files(dest)}
    return attempt(go)


def case_dl_zip_entry_traversal(model_dir):
    """Archive entry ``../../evil/IWFM_C_x64.dll`` must not escape dest."""
    import iwfm_io.dll.download as dl
    t = _workspace(model_dir, "dl_zip_entry_traversal")
    z = t / "trav.zip"
    sha = _make_zip(z, inner_name="../../evil/IWFM_C_x64.dll")
    _mock_fetch(z)
    _register("9.9.9", sha)
    dest = t / "v_trav"

    def go():
        r = attempt(lambda: dl.download_dll("9.9.9", dest_dir=str(dest), show_progress=False))
        evil = [str(p) for p in t.parent.rglob("evil")]
        return {"call": r, "escaped": evil, "dest_files": _dll_files(dest)}
    return attempt(go)


def case_dl_fake_payload_rejected(model_dir):
    """A hash-valid archive whose DLL is not a PE image: download_dll must
    refuse it (or at least load_dll must fail cleanly) and leave no
    unusable DLL installed."""
    import iwfm_io.dll.download as dl
    from iwfm_io.dll import load_dll
    t = _workspace(model_dir, "dl_fake_payload_rejected")
    z = t / "fake.zip"
    sha = _make_zip(z)
    _mock_fetch(z)
    _register("8.8.8", sha)
    dest = t / "v_fake"

    def go():
        r = attempt(lambda: dl.download_dll("8.8.8", dest_dir=str(dest), show_progress=False))
        out = {"download": r, "dest_files": _dll_files(dest)}
        if r["outcome"] == "returned":
            out["load"] = attempt(lambda: str(load_dll(dll_path=r["value"])._name))
            out["still_on_disk"] = os.path.exists(r["value"])
        return out
    return attempt(go)


def case_dl_force_over_loaded_dll(model_dir):
    """force=True while the target DLL is loaded (file locked on Windows):
    either succeeds or fails cleanly, never leaves a truncated DLL."""
    import iwfm_io.dll.download as dl
    from iwfm_io.dll import load_dll
    t = _workspace(model_dir, "dl_force_over_loaded_dll")
    payload = _real_dll_bytes()
    z = t / "real.zip"
    sha = _make_zip(z, payload=payload)
    _mock_fetch(z)
    _register("7.7.7", sha)
    dest = t / "v_loaded"

    def go():
        p = dl.download_dll("7.7.7", dest_dir=str(dest), show_progress=False)
        dll = load_dll(dll_path=p)
        size_before = os.path.getsize(p)
        second = attempt(lambda: dl.download_dll("7.7.7", dest_dir=str(dest), force=True, show_progress=False))
        return {"loaded": str(dll._name), "second": second, "size_before": size_before,
                "size_after": os.path.getsize(p), "intact": os.path.getsize(p) == len(payload)}
    return attempt(go)


def case_dl_fetch_raises_no_leftovers(model_dir):
    """_fetch writes the temp zip then raises: the error propagates, no
    DLL is installed and the temp zip is removed."""
    import iwfm_io.dll.download as dl
    t = _workspace(model_dir, "dl_fetch_raises_no_leftovers")
    z = t / "real2.zip"
    sha = _make_zip(z, payload=_real_dll_bytes())
    _register("6.6.6", sha)
    _mock_fetch(z, raise_after=ConnectionResetError("boom mid-way"))
    dest = t / "v_partial"
    tmp = Path(tempfile.gettempdir())

    def go():
        before = {p.name for p in tmp.glob("*.zip")}
        r = attempt(lambda: dl.download_dll("6.6.6", dest_dir=str(dest), show_progress=False))
        new_zips = sorted({p.name for p in tmp.glob("*.zip")} - before)
        return {"call": r, "dest_files": _dll_files(dest), "new_tmp_zips": new_zips}
    return attempt(go)


def case_dl_version_traversal(model_dir):
    import iwfm_io.dll.download as dl
    t = _workspace(model_dir, "dl_version_traversal")
    _mock_fetch(t / "never.zip")
    return attempt(lambda: dl.download_dll("../../x", show_progress=False))


def case_dl_dest_dir_is_file(model_dir):
    import iwfm_io.dll.download as dl
    t = _workspace(model_dir, "dl_dest_dir_is_file")
    f = t / "afile"
    f.write_text("x")
    z = t / "tiny.zip"
    sha = _make_zip(z, payload=b"x")
    _mock_fetch(z)
    _register("5.5.5", sha)
    return attempt(lambda: dl.download_dll("5.5.5", dest_dir=str(f), show_progress=False))


def case_dl_autodownload_fake_via_load_dll(model_dir):
    """load_dll(version=) auto-fetches a published build: a fake payload
    must not end up installed under the user DLL dir."""
    from iwfm_io.dll import list_dll_versions, load_dll
    t = _workspace(model_dir, "dl_autodownload")
    user = Path(t) / "userdlls"
    z = t / "fake2.zip"
    sha = _make_zip(z)
    _mock_fetch(z)
    _register("4.4.4", sha)

    def go():
        r = attempt(lambda: str(load_dll(version="4.4.4")._name))
        return {"load": r,
                "installed": os.path.exists(user / "4.4.4" / "IWFM_C_x64.dll"),
                "listed": [v for v in list_dll_versions() if v == "4.4.4"]}
    return attempt(go)


# -- load_dll resolution ------------------------------------------------------------------

def _load(model_dir, **kw):
    from iwfm_io.dll import load_dll
    _redirect_user_dlls(model_dir)
    return attempt(lambda: str(load_dll(**kw)._name))


def case_load_version_unknown_no_download(model_dir):
    return _load(model_dir, version="9.9.9", download=False)


def case_load_version_unknown_download_default(model_dir):
    """Unpublished version: the download path must not be attempted."""
    import iwfm_io.dll.download as dl
    calls = []

    def _fetch(url, dest, show_progress):
        calls.append(url)
        raise AssertionError("network fetch attempted")
    dl._fetch = _fetch
    r = _load(model_dir, version="9.9.9")
    r["fetch_calls"] = calls
    return r


def case_load_version_empty(model_dir):
    return _load(model_dir, version="")


def case_load_version_traversal(model_dir):
    return _load(model_dir, version="../x")


def case_load_version_traversal_to_other_version(model_dir):
    """``"2025.0.1747/../2015.0.1403"`` must be rejected, not resolve to
    the 2015 DLL through the path join."""
    return _load(model_dir, version="2025.0.1747/../2015.0.1403")


def case_load_version_absolute_path(model_dir):
    return _load(model_dir, version=os.environ.get("SystemRoot", "C:\\Windows"))


def case_load_version_int(model_dir):
    return _load(model_dir, version=123)


def case_load_path_non_dll_file(model_dir):
    from common import REPO_ROOT
    return _load(model_dir, dll_path=str(REPO_ROOT / "pyproject.toml"))


def case_load_path_directory(model_dir):
    from common import REPO_ROOT
    return _load(model_dir, dll_path=str(REPO_ROOT / "dlls"))


def case_load_path_missing(model_dir):
    return _load(model_dir, dll_path=str(Path(model_dir).parent / "nope" / "IWFM_C_x64.dll"))


def case_load_path_foreign_dll(model_dir):
    """A real Windows DLL that is not IWFM: load_dll must reject it (no
    IWFM exports) instead of returning a half-registered handle."""
    from iwfm_io.dll import load_dll
    from iwfm_io.dll.misc import get_version
    k32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "kernel32.dll")

    def go():
        r = attempt(lambda: str(load_dll(dll_path=k32)._name))
        out = {"load": r}
        if r["outcome"] == "returned":
            out["get_version"] = attempt(lambda: get_version(load_dll(dll_path=k32)))
        return out
    return attempt(go)


def case_load_env_version_garbage(model_dir):
    """IWFM_DLL_VERSION=garbage -> documented fallback to the default version."""
    os.environ["IWFM_DLL_VERSION"] = "garbage!!"
    try:
        return _load(model_dir)
    finally:
        del os.environ["IWFM_DLL_VERSION"]


def case_load_env_version_traversal(model_dir):
    os.environ["IWFM_DLL_VERSION"] = "..\\..\\Windows\\System32"
    try:
        return _load(model_dir)
    finally:
        del os.environ["IWFM_DLL_VERSION"]


def case_load_env_version_2015(model_dir):
    from iwfm_io.dll import list_dll_versions
    if "2015.0.1403" not in list_dll_versions():
        from common import skipped
        return skipped("2015.0.1403 DLL not installed")
    os.environ["IWFM_DLL_VERSION"] = "2015.0.1403"
    try:
        return _load(model_dir)
    finally:
        del os.environ["IWFM_DLL_VERSION"]


if __name__ == "__main__":
    main(globals())
