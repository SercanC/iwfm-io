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
