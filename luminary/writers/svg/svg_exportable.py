"""Base class for objects that can export to SVG format."""

from abc import ABC, abstractmethod
from typing import List


class SVGExportable(ABC):
    """Abstract base class for objects that can generate SVG representations."""

    @abstractmethod
    def get_svg(self) -> List[str]:
        """
        Generate SVG elements for this object.

        Returns:
            List of SVG element strings in proper layering order
        """
        pass
