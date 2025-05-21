# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Variables.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeAlias

from freecad.vars.utils import get_unique_name
from freecad.vars.vendor.fcapi.fpo import PropertyMode
from freecad.vars.config import preferences

import FreeCAD as App  # type: ignore
from collections.abc import Callable
import contextlib

if TYPE_CHECKING:
    from FreeCAD import Document, DocumentObject  # type: ignore


VarOptions: TypeAlias = list[str] | Callable[[], list[str]] | None


def get_vars_group(doc: Document | None = None) -> DocumentObject:
    """
    Return the document object group where all variables are stored.

    :param doc: The document to search in. Defaults to the active document.
    :return: The group where variables are stored.
    """
    doc = doc or App.activeDocument()
    group = doc.getObject("XVarGroup")
    if not group:
        group = doc.addObject("App::DocumentObjectGroup", "XVarGroup")
        group.Label = "Variables"
    return group


def create_var(
    *,
    name: str,
    var_type: str,
    value: Any | None = None,
    options: VarOptions = None,
    description: str = "",
    expression: str | None = None,
    group: str = "Default",
    doc: Document | None = None,
) -> bool:
    """
    Create a variable in a document.

    :param name: The label name of the variable.
    :param var_type: The type of the variable (App::Property*).
    :param value: The value of the variable, defaults to None.
    :param options: A list of options for the variable if var_type is "App::PropertyEnumeration",
                    defaults to None.
    :param str description: The description of the variable, defaults to "".
    :param expression: The expression to calculate the value of the variable, defaults to None.
    :param group: The group where to create the variable, defaults to "Default".
    :param doc: The document where to create the variable, defaults to the active document.
    :return: True if the variable was created, False otherwise.
    """
    name = sanitize_var_name(name)
    doc = doc or App.activeDocument()

    if exists_var_name(name, doc):
        return False

    if var_type == "App::PropertyEnumeration":
        if options is None:
            msg = "options must be provided if var_type is App::PropertyEnumeration"
            raise ValueError(msg)
    elif options is not None:
        msg = "options must be None if var_type is not App::PropertyEnumeration"
        raise ValueError(msg)

    varset: DocumentObject = doc.addObject("App::VarSet", get_unique_name(doc))
    varset.Label = name
    if hasattr(varset, "Label2"):
        varset.Label2 = description
    if callable(options):
        options = options()
    varset.addProperty(var_type, "Value", "", description, enum_vals=options)
    varset.addProperty(
        "App::PropertyString",
        "Description",
        "",
        "Variable Description",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.addProperty(
        "App::PropertyString",
        "VarGroup",
        "",
        "Variable Group",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    if expression:
        varset.setExpression("Value", expression, "Calculated")
        varset.recompute()
    elif value is not None:
        varset.Value = value

    varset.VarGroup = (group or "Default").title()
    varset.Description = description or ""

    if preferences.hide_varsets():
        varset.ViewObject.ShowInTree = False

    get_vars_group(doc).addObject(varset)

    return True


def rename_var(
    name: str,
    new_name: str,
    description: str | None = None,
    doc: Document | None = None,
) -> bool:
    """
    Rename a variable.

    :param name: The label name of the variable to rename.
    :param new_name: The new label name of the variable.
    :param description: The new description of the variable, if any.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and renamed, False otherwise.
    """
    new_name = sanitize_var_name(new_name)
    doc = doc or App.activeDocument()

    if (actual_name := exists_var_name(new_name, doc)) and actual_name.lower() != name.lower():
        return False

    if varset := get_varset(name, doc):
        varset.Label = new_name
        if description:
            varset.setDocumentationOfProperty("Value", description)
            if hasattr(varset, "Description"):
                varset.Description = description
            if hasattr(varset, "Label2"):
                varset.Label2 = description
        doc.recompute()
        return True
    return False


def delete_var(name: str, doc: Document | None = None) -> bool:
    """
    Delete a variable.

    :param name: The label name of the variable to delete.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and deleted, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        doc.removeObject(varset.Name)
        return True
    return False


def get_var(name: str, doc: Document | None = None) -> Any:
    """
    Retrieve the value of a variable by its label name.

    This function searches through the document for objects with the specified
    label name and checks if they have a 'Value' attribute and their name
    starts with 'Var'. If such an object is found, its value is returned.

    :param name: The label name of the variable.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The value of the variable or None if not found.
    """
    doc = doc or App.activeDocument()
    objects: list[DocumentObject] = doc.getObjectsByLabel(name)
    for obj in objects:
        if (value := getattr(obj, "Value", None)) and obj.Name.startswith("XVar_"):
            return value
    return None


def get_varset(name: str, doc: Document | None = None) -> DocumentObject | None:
    """
    Retrieve the variable set (VarSet) object by its label name.

    This function searches through the document for objects with the specified
    label name and checks if they have a 'Value' attribute and their name
    starts with 'Var'. If such an object is found, it is returned.

    :param name: The label name of the variable set to search for.
    :param doc: The document in which to search for the variable set. Defaults
                to the active document if not provided.
    :return: The matching DocumentObject if found, otherwise None.
    """
    doc = doc or App.activeDocument()
    objects: list[DocumentObject] = doc.getObjectsByLabel(name)
    for obj in objects:
        if hasattr(obj, "Value") and obj.Name.startswith("XVar_"):
            return obj
    return None


def set_var(name: str, value: Any, doc: Document | None = None) -> bool:
    """
    Set the value of an existing variable.

    :param name: The name of the variable to set.
    :param value: The new value to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        attr = varset.Value
        if isinstance(attr, App.Units.Quantity):
            if isinstance(value, str):
                varset.Value = App.Units.Quantity(value)
            elif isinstance(value, tuple):
                varset.Value = App.Units.Quantity(*value)
            else:
                varset.Value = value
        else:
            varset.Value = value
        return True
    return False


def set_var_description(name: str, description: str, doc: Document | None = None) -> bool:
    """
    Set the description of an existing variable.

    :param name: The name of the variable to modify.
    :param description: The new description to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        varset.setDocumentationOfProperty("Value", description)
        if hasattr(varset, "Description"):
            varset.Description = description
        if hasattr(varset, "Label2"):
            varset.Label2 = description
        return True
    return False


def set_var_options(name: str, options: VarOptions, doc: Document | None = None) -> bool:
    """
    Set the options of an existing variable.

    :param name: The name of the variable to modify.
    :param options: The new options to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    if options is None:
        msg = "options cannot be None"
        raise ValueError(msg)

    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        varset.Value = options() if callable(options) else options
        return True
    return False


def get_var_options(name: str, doc: Document | None = None) -> list[str]:
    """
    Retrieve the options of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The options of the variable as a list of strings if found, otherwise an empty list.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        return varset.getEnumerationsOfProperty("Value") or []
    return []


def set_var_expression(name: str, expression: str | None, doc: Document | None = None) -> bool:
    """
    Set the expression of an existing variable.

    :param name: The name of the variable to modify.
    :param expression: The new expression to assign to the variable.
                       If None, the expression is cleared.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        if not expression:
            varset.clearExpression(name)
            return True
        varset.setExpression(name, expression)
        return True
    return False


def get_var_expression(name: str, doc: Document | None = None) -> str | None:
    """
    Retrieve the expression associated with a variable.

    This function searches for the expression linked to the specified variable
    within the document's expression engine. If the variable has an expression
    associated with it, the expression is returned.

    :param name: The label name of the variable.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The expression as a string if found, otherwise None.
    """
    doc = doc or App.activeDocument()
    if (varset := get_varset(name, doc)) and varset.ExpressionEngine:
        for prop, expr, *_ in varset.ExpressionEngine:
            if prop == "Value":
                return expr
    return None


def set_var_group(name: str, group: str, doc: Document | None = None) -> bool:
    """
    Set the group of an existing variable.

    :param name: The name of the variable to modify.
    :param group: The new group to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        varset.VarGroup = (group or "Default").title()
        return True
    return False


def get_var_group(name: str, doc: Document | None = None) -> str:
    """
    Get the group of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The group of the variable.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        return varset.VarGroup or "Default"
    return "Default"


def sanitize_var_name(name: str) -> str:
    """
    Check if a name is a valid variable name.

    :param name: The name to check.
    :raises ValueError: If the name is invalid.
    """
    name = (name or "").strip()
    if not name or not name.isidentifier():
        msg = f"Invalid var name: '{name}'"
        raise ValueError(msg)
    return name


def is_var(obj: DocumentObject | None) -> bool:
    """
    Check if an object is a variable.

    :param obj: The object to check.
    :return: True if the object is a variable, False otherwise.
    """
    return obj and obj.TypeId == "App::VarSet" and obj.Name.startswith("XVar_")


def get_vars(doc: Document | None = None) -> list[Variable]:
    """
    Retrieve all variable names in a document.

    :param doc: The document where to search for variables. Defaults to ActiveDocument.
    :return: A list of variable names.
    """
    doc = doc or App.activeDocument()
    return [Variable(doc, obj.Label) for obj in doc.findObjects("App::VarSet") if is_var(obj)]


def get_groups(doc: Document | None = None) -> list[str]:
    """
    Retrieve all variable groups in a document.

    :param doc: The document where to search for variables. Defaults to ActiveDocument.
    :return: A list of variable groups.
    """
    doc = doc or App.activeDocument()
    existing_groups = {obj.VarGroup for obj in doc.findObjects("App::VarSet") if is_var(obj)}
    existing_groups.add("Default")
    return sorted(existing_groups)


def set_var_type(
    name: str,
    new_type: str,
    doc: Document | None = None,
    converter: Callable | None = None,
) -> bool:
    """
    Set the type of an existing variable.

    :param name: The name of the variable to modify.
    :param var_type: The new type to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        if new_type not in varset.supportedProperties():
            msg = f"Invalid var type: '{new_type}'"
            raise ValueError(msg)

        old_type = varset.getTypeIdOfProperty("Value")
        if old_type == new_type:
            return False

        # Custom converter
        if converter:
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if value:
                with contextlib.suppress(Exception):
                    varset.Value = converter(value)
            return True

        # List to base (use first value if any)
        if old_type == f"{new_type}List":
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if isinstance(value, list) and value:
                varset.Value = value[0]
            return True

        # Base to list
        if new_type == f"{old_type}List":
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if value:
                varset.Value = [value]
            return True

        # Enumeration to base (TODO)

        # List to list
        if old_type.endswith("List") and new_type.endswith("List"):
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if isinstance(value, list):
                with contextlib.suppress(Exception):
                    varset.Value = convert_list_type(value, new_type)
            return True

        # Raw type conversion
        value = varset.Value
        varset.removeProperty("Value")
        varset.addProperty(new_type, "Value", "", varset.Description)
        if value:
            with contextlib.suppress(Exception):
                varset.Value = type(varset.Value)(value)
        return True

    return False


def convert_list_type(data: list, new_type: str) -> list:
    """
    Convert a list of values to a new list with elements cast to a specified type.

    :param list data: The list of values to convert.
    :param str new_type: The type of the new list.
    :return: A new list with the converted values.
    """
    if not data:
        return []
    if new_type == "App::PropertyStringList":
        return [str(item) for item in data]
    if new_type == "App::PropertyIntegerList":
        return [int(item) for item in data]
    if new_type == "App::PropertyFloatList":
        return [float(item) for item in data]
    return []


def export_variables(path: str | Path, doc: Document | None = None) -> bool:
    """
    Export variables to a file.

    :param path: The path to the file where the variables will be exported.
    :param doc: The document where to export the variables. Defaults to ActiveDocument.
    :return: True if the export was successful, False otherwise.
    """
    from .files import save_variables_to_file, VarInfoData

    if not path:
        return False

    path = Path(path)
    doc = doc or App.activeDocument()

    variables = get_vars(doc)

    var_info_list = [
        VarInfoData(
            type=var.var_type,
            name=var.name,
            value=var.value,
            internal_name=var.internal_name,
            description=var.description,
            group=var.group,
            expression=var.expression,
            options=var.options,
        )
        for var in variables
    ]

    save_variables_to_file(path, var_info_list)
    return True


def import_variables(path: str | Path, doc: Document | None = None) -> bool:
    """
    Import variables from a file.

    :param path: The path to the file from which the variables will be imported.
    :param doc: The document where to import the variables. Defaults to ActiveDocument.
    :return: True if the import was successful, False otherwise.
    """
    from .files import load_variables_from_file
    from .properties import get_supported_property_types

    if not path:
        return False

    path = Path(path)
    doc = doc or App.activeDocument()

    variables = load_variables_from_file(path)
    supported = get_supported_property_types()

    for var in variables:
        if var.type not in supported:
            App.Console.PrintError(
                f"Variable '{var.name}' type '{var.type}' is not supported. (Not imported)\n",
            )
            continue

        doc_var = Variable(doc, var.name)
        if doc_var.exists():
            if doc_var.var_type != var.type:
                App.Console.PrintError(
                    f"Variable '{var.name}' already exists with a different type. (Not imported)\n",
                )
                continue
        else:
            doc_var.create_if_not_exists(
                var_type=var.type,
                options=var.options,
                description=var.description,
                expression=var.expression,
            )

        if var.value is not None:
            try:
                doc_var.value = var.value
            except Exception:  # noqa: BLE001
                App.Console.PrintError(
                    f"Variable '{var.name}' value ({var.value}) is not valid. (Ignored)\n",
                )

    return True


class Variable:
    """
    A wrapper class for a variable.
    """

    _name: str
    _doc: Document

    def __init__(self, doc: Document, name: str) -> None:
        """
        Initialize a Variable proxy (does not create the variable).

        :param doc: The document associated with the variable.
        :param name: The name of the variable.
        :raises ValueError: If the document is None or the name is invalid.
        """
        if not doc:
            msg = "doc cannot be None"
            raise ValueError(msg)

        name = sanitize_var_name(name)
        self._name = name
        self._doc = doc

    def create_if_not_exists(
        self,
        var_type: str = "App::PropertyLength",
        default: Any = None,
        options: VarOptions = None,
        description: str = "",
        expression: str | None = None,
    ) -> Variable:
        """
        Create a variable if it doesn't exist.

        If the variable doesn't exist, it is created with the given arguments.
        If the variable already exists, it is not modified.

        :param var_type: The type of the variable, defaults to 'App::PropertyLength'.
        :param default: The default value of the variable, defaults to None.
        :param options: The options for the variable if var_type is 'App::PropertyEnumeration',
                        defaults to None.
        :param description: The description of the variable, defaults to "".
        :param expression: The expression to calculate the value of the variable, defaults to None.
        :return: self
        """
        create_var(
            name=self._name,
            var_type=var_type,
            value=default,
            options=options,
            description=description,
            expression=expression,
            doc=self._doc,
        )
        return self

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Any:
        return get_var(self._name, self._doc)

    @value.setter
    def value(self, value: Any) -> None:
        set_var(self._name, value, self._doc)

    def rename(self, new_name: str) -> bool:
        if rename_var(self._name, new_name, doc=self._doc):
            self._name = new_name
            return True
        return False

    @property
    def options(self) -> list[str]:
        return get_var_options(self._name, self._doc)

    @options.setter
    def options(self, options: VarOptions) -> None:
        set_var_options(self._name, options, doc=self._doc)

    @property
    def expression(self) -> str | None:
        return get_var_expression(self._name, doc=self._doc)

    @expression.setter
    def expression(self, expression: str | None) -> None:
        set_var_expression(self._name, expression, doc=self._doc)

    def __repr__(self) -> str:
        return f"Variable(name={self._name}, value={self.value})"

    def exists(self) -> bool:
        return bool(exists_var_name(self._name, self._doc))

    def delete(self) -> bool:
        return delete_var(self._name, doc=self._doc)

    @property
    def dependencies(self) -> list[DocumentObject]:
        if varset := get_varset(self._name, self._doc):
            return list(set(varset.OutList)) or []
        return []

    @property
    def references(self) -> list[DocumentObject]:
        if varset := get_varset(self._name, self._doc):
            return list(set(varset.InList)) or []
        return []

    @property
    def description(self) -> str:
        if varset := get_varset(self._name, self._doc):
            return (
                getattr(varset, "Description", "")
                or varset.getDocumentationOfProperty("Value")
                or ""
            )
        return ""

    @description.setter
    def description(self, description: str) -> None:
        set_var_description(self._name, description, doc=self._doc)

    @property
    def group(self) -> str:
        return get_var_group(self._name, doc=self._doc)

    @group.setter
    def group(self, group: str) -> None:
        set_var_group(self._name, group, doc=self._doc)

    @property
    def var_type(self) -> str | None:
        if varset := get_varset(self._name, self._doc):
            return varset.getTypeIdOfProperty("Value")
        return None

    @property
    def varset(self) -> DocumentObject | None:
        return get_varset(self._name, self._doc)

    @property
    def internal_name(self) -> str | None:
        if varset := get_varset(self._name, self._doc):
            return varset.Name
        return None

    @property
    def doc(self) -> Document:
        return self._doc

    def change_var_type(
        self,
        new_type: str,
        converter: Callable | None = None,
    ) -> bool:
        return set_var_type(
            self._name,
            new_type,
            doc=self._doc,
            converter=converter,
        )


def exists_var_name(name: str, doc: Document | None = None) -> str | None:
    """
    Check if a variable name exists in the document (case insensitive).

    :param name: The name of the variable to check.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The variable name if it exists, None otherwise.
    """
    doc = doc or App.activeDocument()
    name = name.lower()
    for obj in doc.findObjects("App::VarSet"):
        if is_var(obj) and obj.Label.lower() == name:
            return obj.Label
    return None
