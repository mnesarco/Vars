# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations
from freecad.vars.vendor.fcapi import fcui as ui
from typing import Any

class _ThemeColorsHack(ui.QLabel):
    def paintEvent(self, _e: ui.QPaintEvent) -> None:
        qp = ui.QPainter()
        qp.begin(self)
        qp.fillRect(0, 0, 5, 10, qp.pen().color())
        qp.end()

# This is a hack to obtain the text color depending on the current stylesheet
# There is no way to get stylesheet info directly in Qt
def get_base_colors() -> tuple[ui.Color, ui.Color]:
    lb = _ThemeColorsHack()
    lb.setGeometry(0,0,10,10)
    pixmap = ui.QPixmap(10,10)
    lb.render(pixmap)
    image = pixmap.toImage()
    background = image.pixelColor(9,5)
    color = image.pixelColor(1,5)
    return ui.Color(color), ui.Color(background)

TEXT_COLOR, BG_COLOR = get_base_colors()
ICON_COLOR = ui.Color(TEXT_COLOR, alpha=0.75)

def FlatIcon(path: str) -> ui.ColorIcon:
    return ui.ColorIcon(path, ICON_COLOR)

def interpolate_style_vars(template: str, variables: dict[str, Any]) -> str:
    """
    Apply the template to the vars and return the result.
    """
    for k, v in variables.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template
