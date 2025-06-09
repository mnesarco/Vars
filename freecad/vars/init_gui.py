# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

# ruff: noqa: F401

from . import commands
from . import config

from .vendor.fcapi.preferences import Preference
from .vendor.fcapi.workbenches import Rules

config.commands.install()

rules = Rules("Vars_WBM")

# Tools menu
rules.toolbar_insert(commands.EditVars.name, before="Std_VarSet")

rules.install()


@Preference.subscribe(config.preferences.group)
def on_user_pref_changed(group: object, _type: type, name: str, _value: object) -> None:
    from freecad.vars.core import variables
    from itertools import chain

    if name == config.VarsPreferences.hide_varsets.name:
        show = not config.preferences.hide_varsets()
        if group := variables.get_vars_group():
            for obj in chain(group.Group, [group]):
                if view := getattr(obj, "ViewObject", None):
                    view.ShowInTree = show
