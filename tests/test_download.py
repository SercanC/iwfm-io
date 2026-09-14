"""Tests for iwfm_io.dll.download_dll (no network required)."""

import hashlib
import io
import os
import urllib.error
import urllib.request
import zipfile

import pytest

from iwfm_io.dll.download import KNOWN_DLLS, _RELEASE_URL, download_dll


def test_unknown_version_raises_with_available_list():
    with pytest.raises(ValueError) as exc:
        download_dll("0.0.0")
    assert "0.0.0" in str(exc.value)
    assert "2025.0.1747" in str(exc.value)


def test_known_dlls_have_sha256():
    for version, digest in KNOWN_DLLS.items():
        assert len(digest) == 64
        int(digest, 16)  # valid hex
        assert "{version}" in _RELEASE_URL


def test_already_installed_short_circuits(tmp_path):
    dll = tmp_path / "IWFM_C_x64.dll"
    dll.write_bytes(b"stub")
    result = download_dll("2025.0.1747", dest_dir=tmp_path,
                          show_progress=False)
    assert result == str(dll)
    assert dll.read_bytes() == b"stub"  # untouched, no download


class TestLoadDllFetchOnMiss:
    """load_dll(version=...) fetches published builds on a cache miss."""

    def _isolate(self, monkeypatch, tmp_path):
        """Point both DLL search roots at empty temp dirs."""
        from iwfm_io.dll import _dll
        monkeypatch.setattr(_dll, "_PROJECT_DLLS", str(tmp_path / "proj"))
        monkeypatch.setattr(_dll, "_USER_DLLS", str(tmp_path / "user"))
        return _dll

    def test_download_invoked_on_miss(self, monkeypatch, tmp_path):
        from iwfm_io.dll import download as dl
        _dll = self._isolate(monkeypatch, tmp_path)

        calls = []
        monkeypatch.setitem(dl.KNOWN_DLLS, "9.9.9", "0" * 64)
        monkeypatch.setattr(dl, "download_dll",
                            lambda version, **kw: calls.append(version))

        # The fake downloader installs nothing, so resolution still fails —
        # but it must have been invoked with the requested version.
        with pytest.raises(FileNotFoundError):
            _dll.load_dll(version="9.9.9")
        assert calls == ["9.9.9"]

    def test_download_false_preserves_search_only(self, monkeypatch, tmp_path):
        from iwfm_io.dll import download as dl
        _dll = self._isolate(monkeypatch, tmp_path)

        monkeypatch.setitem(dl.KNOWN_DLLS, "9.9.9", "0" * 64)
        monkeypatch.setattr(
            dl, "download_dll",
            lambda *a, **kw: pytest.fail("download_dll must not be called"))

        with pytest.raises(FileNotFoundError) as exc:
            _dll.load_dll(version="9.9.9", download=False)
        assert "download=False" in str(exc.value)

    def test_unpublished_version_not_downloaded(self, monkeypatch, tmp_path):
        from iwfm_io.dll import download as dl
        _dll = self._isolate(monkeypatch, tmp_path)

        monkeypatch.setattr(
            dl, "download_dll",
            lambda *a, **kw: pytest.fail("download_dll must not be called"))

        with pytest.raises(FileNotFoundError):
            _dll.load_dll(version="0.0.0-unpublished")

    def test_download_failure_is_reported(self, monkeypatch, tmp_path):
        from iwfm_io.dll import download as dl
        _dll = self._isolate(monkeypatch, tmp_path)

        def _boom(version, **kw):
            raise RuntimeError("network unreachable")

        monkeypatch.setitem(dl.KNOWN_DLLS, "9.9.9", "0" * 64)
        monkeypatch.setattr(dl, "download_dll", _boom)

        with pytest.raises(FileNotFoundError) as exc:
            _dll.load_dll(version="9.9.9")
        assert "network unreachable" in str(exc.value)


# ---------------------------------------------------------------------------
# resumable fetch (no network: urllib.request.urlopen is faked)
# ---------------------------------------------------------------------------

def _fake_dll_bytes(size=4096):
    """A minimal Windows PE image: MZ header, e_lfanew -> 'PE\\0\\0'."""
    head = bytearray(b"MZ" + b"\0" * 0x3E)
    head[0x3C:0x40] = (0x80).to_bytes(4, "little")
    body = bytearray(b"\0" * (0x80 - len(head))) + b"PE\0\0"
    payload = bytes(head) + bytes(body)
    return payload + bytes(range(256)) * ((size - len(payload)) // 256 + 1)


def _fake_release_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("IWFM_C_x64.dll", _fake_dll_bytes())
        zf.writestr("README.txt", "fake release asset\n")
    return buf.getvalue()


class _FakeResponse:
    """What ``urllib.request.urlopen`` returns: a context manager with
    ``.status``, ``.headers`` and chunked ``.read()``."""

    def __init__(self, body, status, headers):
        self._buf = io.BytesIO(body)
        self.status = status
        self.headers = headers

    def read(self, n=-1):
        return self._buf.read(n)

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeServer:
    """Serves one asset; ``ranges=True`` honours ``Range`` with 206."""

    def __init__(self, asset, ranges=True):
        self.asset = asset
        self.ranges = ranges
        self.requests = []      # the Range header of every request

    def __call__(self, req, timeout=None):
        rng = req.headers.get("Range")
        self.requests.append(rng)
        if rng and self.ranges:
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= len(self.asset):
                raise urllib.error.HTTPError(
                    req.full_url, 416, "Range Not Satisfiable", {}, None)
            body = self.asset[start:]
            return _FakeResponse(body, 206, {
                "Content-Length": str(len(body)),
                "Content-Range": (f"bytes {start}-{len(self.asset) - 1}/"
                                  f"{len(self.asset)}"),
            })
        return _FakeResponse(self.asset, 200,
                             {"Content-Length": str(len(self.asset))})


@pytest.fixture
def fake_asset(monkeypatch):
    """Register version 9.9.9 with a fake zip and expose its bytes."""
    from iwfm_io.dll import download as dl
    asset = _fake_release_zip()
    monkeypatch.setitem(dl.KNOWN_DLLS, "9.9.9",
                        hashlib.sha256(asset).hexdigest())
    return asset


def _install(monkeypatch, server, tmp_path):
    monkeypatch.setattr(urllib.request, "urlopen", server)
    return download_dll("9.9.9", dest_dir=tmp_path, show_progress=False)


def _partial_path(tmp_path):
    return tmp_path / "IWFM_C_x64-9.9.9.zip.part"


def test_fresh_download_installs_and_cleans_up(monkeypatch, tmp_path,
                                               fake_asset):
    server = _FakeServer(fake_asset)
    dll = _install(monkeypatch, server, tmp_path)
    assert server.requests == [None]             # no Range on a fresh fetch
    assert os.path.isfile(dll)
    assert open(dll, "rb").read(2) == b"MZ"
    assert sorted(os.listdir(tmp_path)) == ["IWFM_C_x64.dll"]


def test_resume_from_partial_file(monkeypatch, tmp_path, fake_asset):
    cut = len(fake_asset) // 3
    _partial_path(tmp_path).write_bytes(fake_asset[:cut])
    server = _FakeServer(fake_asset, ranges=True)

    dll = _install(monkeypatch, server, tmp_path)

    assert server.requests == [f"bytes={cut}-"]   # one ranged request
    assert os.path.isfile(dll)
    assert open(dll, "rb").read(2) == b"MZ"
    assert not _partial_path(tmp_path).exists()  # archive disposed of
    assert not os.path.exists(dll + ".part")


def test_server_without_range_support_restarts(monkeypatch, tmp_path,
                                               fake_asset):
    cut = len(fake_asset) // 2
    _partial_path(tmp_path).write_bytes(fake_asset[:cut])
    server = _FakeServer(fake_asset, ranges=False)   # answers 200

    dll = _install(monkeypatch, server, tmp_path)

    assert server.requests == [f"bytes={cut}-"]
    assert os.path.isfile(dll)
    assert open(dll, "rb").read(2) == b"MZ"
    assert not _partial_path(tmp_path).exists()


def test_hash_mismatch_after_resume_installs_nothing(monkeypatch, tmp_path,
                                                     fake_asset):
    """A partial file from a different (or corrupted) download resumes
    cleanly at the byte level but fails the sha256 check: no DLL, and
    the bad partial is discarded so the next call starts clean."""
    cut = len(fake_asset) // 3
    _partial_path(tmp_path).write_bytes(b"x" * cut)   # wrong head bytes
    server = _FakeServer(fake_asset, ranges=True)

    with pytest.raises(RuntimeError, match="integrity"):
        _install(monkeypatch, server, tmp_path)

    assert server.requests == [f"bytes={cut}-"]
    assert not (tmp_path / "IWFM_C_x64.dll").exists()
    assert not (tmp_path / "IWFM_C_x64.dll.part").exists()
    assert not _partial_path(tmp_path).exists()

    # ... and a second attempt succeeds from scratch
    server2 = _FakeServer(fake_asset, ranges=True)
    dll = _install(monkeypatch, server2, tmp_path)
    assert server2.requests == [None]
    assert os.path.isfile(dll)


def test_interrupted_fetch_keeps_partial_for_resume(monkeypatch, tmp_path,
                                                    fake_asset):
    """A network error mid-stream leaves the bytes received so far in
    the .part file; the next call resumes exactly there."""
    cut = len(fake_asset) // 2

    class _Dropping(_FakeServer):
        def __call__(self, req, timeout=None):
            resp = super().__call__(req, timeout)
            resp._buf = io.BytesIO(self.asset[:cut])   # then the pipe dies

            def read(n=-1, _r=resp._buf.read):
                chunk = _r(n)
                if not chunk:
                    raise urllib.error.URLError("connection reset")
                return chunk
            resp.read = read
            return resp

    with pytest.raises(urllib.error.URLError):
        _install(monkeypatch, _Dropping(fake_asset), tmp_path)
    assert _partial_path(tmp_path).read_bytes() == fake_asset[:cut]

    server = _FakeServer(fake_asset, ranges=True)
    dll = _install(monkeypatch, server, tmp_path)
    assert server.requests == [f"bytes={cut}-"]
    assert os.path.isfile(dll)


def test_range_not_satisfiable_restarts(monkeypatch, tmp_path, fake_asset):
    """A partial file longer than the asset (416) is discarded."""
    _partial_path(tmp_path).write_bytes(fake_asset + b"junk")
    server = _FakeServer(fake_asset, ranges=True)

    dll = _install(monkeypatch, server, tmp_path)

    assert server.requests == [f"bytes={len(fake_asset) + 4}-", None]
    assert os.path.isfile(dll)
