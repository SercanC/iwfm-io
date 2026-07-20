"""Regression tests for DLL-generation-aware IW_Model_New.

The 2015-line DLLs take a 7-argument IW_Model_New (no model-id
out-parameter); calling the 8-argument form made the DLL write iStat into
the model-id slot, silently swallowing open failures.  These tests need
locally installed DLL builds and skip when they are absent.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="IWFM DLL is Windows-only")


def _find(version):
    from iwfm_io.dll._dll import _find_version
    return _find_version(version)


class TestModelNewGenerations:
    @pytest.mark.parametrize("version", ["2015.3.1443", "2025.0.1747"])
    def test_open_failure_raises(self, version):
        """A bad preprocessor path must raise IWFMError on both DLL lines."""
        if _find(version) is None:
            pytest.skip(f"DLL {version} not installed")
        from iwfm_io.dll import IWFMModel
        from iwfm_io.dll._errors import IWFMError

        with pytest.raises(IWFMError):
            IWFMModel("nonexistent_pp.in", "nonexistent_sim.in",
                      is_for_inquiry=True, dll_version=version)

    @pytest.mark.parametrize("version,multi", [
        ("2015.3.1443", False),
        ("2025.0.1747", True),
    ])
    def test_generation_detection(self, version, multi):
        if _find(version) is None:
            pytest.skip(f"DLL {version} not installed")
        from iwfm_io.dll._dll import load_dll

        dll = load_dll(version=version)
        assert dll._iwfm_multi_model is multi
        # Registered constructor signature matches the generation
        n_args = len(dll.IW_Model_New.argtypes)
        assert n_args == (8 if multi else 7)
