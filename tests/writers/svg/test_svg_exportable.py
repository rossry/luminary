"""Tests for SVGExportable base class."""

import pytest
from luminary.writers.svg.svg_exportable import SVGExportable


class TestImplementation(SVGExportable):
    """Test implementation of SVGExportable."""

    def get_svg(self):
        return ["<circle cx='0' cy='0' r='5'/>"]


class TestSVGExportable:
    """Test cases for SVGExportable base class."""

    def test_abstract_base_class(self):
        """Test that SVGExportable cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SVGExportable()

    def test_concrete_implementation(self):
        """Test that concrete implementations work correctly."""
        impl = TestImplementation()
        result = impl.get_svg()
        assert result == ["<circle cx='0' cy='0' r='5'/>"]
        assert isinstance(impl, SVGExportable)

    def test_missing_implementation_fails(self):
        """Test that classes without get_svg implementation fail."""

        class IncompleteImpl(SVGExportable):
            pass

        with pytest.raises(TypeError):
            IncompleteImpl()
