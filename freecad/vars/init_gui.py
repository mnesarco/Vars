# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

# ruff: noqa: F401

from . import commands
from . import config

from .vendor.fcapi.workbenches import Rules

config.commands.install()

rules = Rules("Vars_WBM")

# Tools menu
rules.toolbar_insert(commands.EditVars.name, before="Std_VarSet")

rules.install()
