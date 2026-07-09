"""Tests for validation module."""

import pytest
from pathlib import Path

from tests.io.conftest import PREPROCESSOR_DIR


class TestValidation:
    def test_validate_nodes(self):
        from iwfm_io.readers.preprocessor import read_nodes
        from iwfm_io._validation import validate_nodes

        path = PREPROCESSOR_DIR / "NodeXY.dat"
        if path.exists():
            nf = read_nodes(path)
            errors = validate_nodes(nf)
            assert isinstance(errors, list)
            # Sample model should have no errors
            assert len(errors) == 0

    def test_validate_elements(self):
        from iwfm_io.readers.preprocessor import read_nodes, read_elements
        from iwfm_io._validation import validate_elements

        node_path = PREPROCESSOR_DIR / "NodeXY.dat"
        elem_path = PREPROCESSOR_DIR / "Element.dat"
        if node_path.exists() and elem_path.exists():
            nf = read_nodes(node_path)
            ef = read_elements(elem_path, node_file=nf)
            errors = validate_elements(ef, nf)
            assert isinstance(errors, list)
            assert len(errors) == 0

    def test_validate_preprocessor(self):
        from iwfm_io.readers.preprocessor import read_preprocessor_main
        from iwfm_io._validation import validate_preprocessor

        path = PREPROCESSOR_DIR / "PreProcessor_MAIN.IN"
        if path.exists():
            pp = read_preprocessor_main(path, follow_references=True)
            errors = validate_preprocessor(pp)
            assert isinstance(errors, list)
            # May have some warnings but should not crash
