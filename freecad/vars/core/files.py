# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import contextlib

# Property types that are considered literals
LITERALS = {
    "App::PropertyInteger",
    "App::PropertyFloat",
    "App::PropertyStringList",
    "App::PropertyIntegerList",
    "App::PropertyFloatList",
}


@dataclass(kw_only=True)
class VarInfoData:
    """
    Information about a FreeCAD variable for persistence.
    """

    type: str
    name: str
    value: Any
    internal_name: str
    description: str | None = None
    group: str | None = None
    expression: str | None = None
    options: list[str] | None = None


def load_variables_from_file(file_path: str | Path) -> list[VarInfoData]:
    """
    Load variables from a file in INI format and return them as a list of VarInfoData objects.

    :param file_path: The path to the file from which the variables will be loaded.
    :return: A list of VarInfoData objects representing the variables loaded from the file.
    :side effects: Reads from the specified file path.
    """
    import configparser as cp
    import ast

    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    config = cp.ConfigParser()
    config.read(str(file_path))

    variables: list[VarInfoData] = []
    for section in config.sections():
        var_info = VarInfoData(
            type=config.get(section, "type", fallback=None),
            name=section,
            value=config.get(section, "value", fallback=None),
            internal_name=config.get(section, "internal_name", fallback=None),
            description=config.get(section, "description", fallback=""),
            group=config.get(section, "group", fallback="Default"),
            expression=config.get(section, "expression", fallback=None),
            options=config.get(section, "options", fallback=None),
        )
        variables.append(var_info)

    for var in variables:
        if var.options:
            with contextlib.suppress(Exception):
                var.options = ast.literal_eval(var.options)
        if var.value is not None and var.type in LITERALS:
            with contextlib.suppress(Exception):
                var.value = ast.literal_eval(var.value)
    return variables


def save_variables_to_file(file_path: str | Path, variables: list[VarInfoData]) -> None:
    """
    Save a list of variable information objects to a file in INI format.

    :param file_path: The path to the file where the variables will be saved.
    :param variables: The list of VarInfoData objects to persist.
    :return: None
    :side effects: Writes to the specified file path, overwriting its contents if it exists.
    """
    import configparser as cp

    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    config = cp.ConfigParser()
    for var in variables:
        section = var.name
        config.add_section(section)
        config.set(section, "type", var.type)
        if var.value is not None:
            if var.type in LITERALS:
                config.set(section, "value", repr(var.value))
            else:
                config.set(section, "value", str(var.value))
        config.set(section, "internal_name", var.internal_name)
        config.set(section, "group", var.group or "Default")
        if var.description:
            config.set(section, "description", var.description or "")
        if var.expression:
            config.set(section, "expression", var.expression)
        if var.options:
            config.set(section, "options", repr(var.options))

    with file_path.open("w") as f:
        config.write(f)
