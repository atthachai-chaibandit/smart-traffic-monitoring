
from math import ceil
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def get_pixmap(
    name: str,
    color: str = "#A78BFA",
    size: int = 24,
    dpr: float = 1.0,
) -> QPixmap:
    """Render a recolored SVG at the target display's pixel density."""

    path = ICON_DIR / f"{name}.svg"

    if not path.is_file():
        raise FileNotFoundError(f"Icon not found: {path}")

    if not QColor.isValidColor(color):
        raise ValueError(f"Invalid HEX color: {color}")

    if size <= 0:
        raise ValueError("Icon size must be positive")
    if dpr <= 0:
        raise ValueError("Device pixel ratio must be positive")

    # Read SVG
    svg = path.read_text(encoding="utf-8")

    # Replace Tabler's currentColor with the requested HEX
    svg = svg.replace("currentColor", QColor(color).name())

    # Render SVG to transparent pixmap
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    if not renderer.isValid():
        raise ValueError(f"Invalid SVG file: {path}")

    # Allocate physical pixels, but keep painting coordinates in logical units.
    pixels = ceil(size * dpr)
    pixmap = QPixmap(pixels, pixels)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    return pixmap


def get_icon(
    name: str,
    color: str = "#A78BFA",
    size: int = 24,
    dpr: float = 1.0,
) -> QIcon:
    """Return a colored QIcon."""
    return QIcon(get_pixmap(name, color, size, dpr))


def set_button_icon(
    button,
    name: str,
    color: str = "#A78BFA",
    size: int = 20
):
    """Apply a colored icon to a QPushButton."""
    button.setIcon(get_icon(name, color, size, button.devicePixelRatioF()))
    button.setIconSize(QSize(size, size))
