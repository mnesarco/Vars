# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations
from freecad.vars.config import resources, commands
from freecad.vars.vendor.fcapi.lang import dtr
import FreeCAD as App  # type: ignore[import]


@commands.add(
    label=str(dtr("Vars", "Variables")),
    tooltip=str(dtr("Vars", "Edit Variables")),
    icon=resources.icon("vars.svg"),
    accel="Ctrl+Shift+K",
)
class EditVars:
    """
    Show the FreeCAD Vars Gui.
    """

    def on_activated(self) -> None:
        from freecad.vars.ui.editors import VariablesEditor

        _editor = VariablesEditor(App.activeDocument())

    def is_active(self) -> bool:
        return bool(App.GuiUp and App.activeDocument())
