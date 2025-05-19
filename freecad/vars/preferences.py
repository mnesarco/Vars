# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations

from .vendor.fcapi.preferences import (
    Preference,
    Preferences,
    auto_gui,
)
from .vendor.fcapi.lang import dtr


@auto_gui(
    default_ui_group="Vars",
    default_ui_page=dtr("Vars", "General"),
    enable_presets=False,
)
class VarsPreferences(Preferences):
    """
    Vars Import Preferences.
    """

    group = "Preferences/Mod/Vars/General"

    hide_varsets = Preference(
        group,
        name="hide_objects",
        default=True,
        label=dtr("Vars", "Hide internally generated Varsets"),
        description=dtr(
            "Vars",
            "Hide Internal Varsets used to store the variables.",
        ),
        ui_section=dtr("Vars", "General"),
    )

    show_descriptions = Preference(
        group,
        name="show_descriptions",
        default=True,
        label=dtr("Vars", "Show var descriptions in the editor"),
        description=dtr(
            "Vars",
            "Show var descriptions in the editor.",
        ),
        ui_section=dtr("Vars", "General"),
    )

    default_property_type = Preference(
        group,
        name="default_property_type",
        default="App::PropertyLength",
        label=dtr("Vars", "Default property type"),
        description=dtr(
            "Vars",
            "Default property type when creating a new var.",
        ),
        ui_section=dtr("Vars", "General"),
    )
