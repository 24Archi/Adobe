from dataclasses import dataclass, field
from typing import List, Counter

@dataclass
class Line:
    """Represents a line of text with font/layout metadata for heading detection."""
    page: int
    text: str
    font_names: List[str]
    font_sizes: List[float]
    x0: float
    x1: float
    top: float
    bottom: float
    is_boldish: bool
    is_all_caps: bool
    avg_font_size: float
    leading: float
    indent: float 