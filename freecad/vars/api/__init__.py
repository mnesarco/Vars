# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

# ruff: noqa: F401

"""
FreeCAD Vars: Public API.
"""

from freecad.vars.core.variables import (
    create_var,
    delete_var,
    rename_var,
    get_var,
    get_varset,
    get_vars,
    get_groups,
    set_var,
    set_var_description,
    set_var_type,
    set_var_group,
    set_var_expression,
    set_var_options,
    export_variables,
    import_variables,
    Variable,
)
