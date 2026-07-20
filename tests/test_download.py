"""Tests for iwfm_io.dll.download_dll (no network required)."""

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
