# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations

from .vendor.fcapi.preferences import (
    Preference,
    Preferences,
    auto_gui,
)
from .vendor.fcapi.lang import dtr
from freecad.vars.core.properties import get_supported_property_types

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
        label=dtr("Vars", "Hide variables in the Tree View"),
        description=dtr(
            "Vars",
            "Hide associated Varset objects in the document Tree view",
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
        options=get_supported_property_types(),
    )

    class Hidden:
        """
        Preferences for internal use. Nor editable by users.
        """

        show_hidden_vars = Preference(
            group="Preferences/Mod/Vars/Internal",
            name="show_hidden_vars",
            default=False,
        )

