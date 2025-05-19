# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from .vendor.fcapi.resources import Resources
from .vendor.fcapi.commands import CommandRegistry

from . import resources as resources_pkg
from .preferences import VarsPreferences

resources = Resources(resources_pkg)
commands = CommandRegistry("Vars_")
preferences = VarsPreferences()
