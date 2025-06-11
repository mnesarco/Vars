# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Variables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeAlias
import operator as op

from freecad.vars.utils import get_unique_name
from freecad.vars.vendor.fcapi.fpo import PropertyMode
from freecad.vars.config import preferences

import FreeCAD as App  # type: ignore
from collections.abc import Callable
import contextlib
from dataclasses import dataclass

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
    group: DocumentObject = doc.getObject("XVarGroup")
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

    if existing_var_name(name, doc):
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
    varset.Description = description or ""

    varset.addProperty(
        "App::PropertyString",
        "VarGroup",
        "",
        "Variable Group",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.VarGroup = (group or "Default").title()

    varset.addProperty(
        "App::PropertyInteger",
        "SortKey",
        "",
        "Variable Sort Key",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.SortKey = 0

    varset.addProperty(
        "App::PropertyBool",
        "Hidden",
        "",
        "Hide variable from UI",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.Hidden = False

    if expression:
        varset.setExpression("Value", expression, "Calculated")
        varset.recompute()
    elif value is not None:
        varset.Value = value

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
    :return: True if the variable was renamed, False otherwise. raise error if var does not exists.
    """
    return Variable(doc or App.activeDocument(), name).rename(new_name, description)


def delete_var(name: str, doc: Document | None = None) -> bool:
    """
    Delete a variable.

    :param name: The label name of the variable to delete.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and deleted, False otherwise.
    """
    return Variable(doc or App.activeDocument(), name).delete()


def get_var(name: str, doc: Document | None = None) -> Any:
    """
    Retrieve the value of a variable by its label name.

    This function searches through the document for objects with the specified
    label name and checks if they have a 'Value' attribute and their name
    starts with 'Var'. If such an object is found, its value is returned.

    :param name: The label name of the variable.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The value of the variable or raise error if not found.
    """
    return Variable(doc or App.activeDocument(), name).value


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


def set_var(name: str, value: Any, doc: Document | None = None) -> None:
    """
    Set the value of an existing variable.

    :param name: The name of the variable to set.
    :param value: The new value to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).value = value


def set_var_description(name: str, description: str, doc: Document | None = None) -> None:
    """
    Set the description of an existing variable.

    :param name: The name of the variable to modify.
    :param description: The new description to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).description = description


def set_var_options(name: str, options: VarOptions, doc: Document | None = None) -> None:
    """
    Set the options of an existing variable.

    :param name: The name of the variable to modify.
    :param options: The new options to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).options = options


def get_var_options(name: str, doc: Document | None = None) -> list[str]:
    """
    Retrieve the options of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The options of the variable as a list of strings if found, raise otherwise.
    """
    return Variable(doc or App.activeDocument(), name).options


def set_var_expression(name: str, expression: str | None, doc: Document | None = None) -> None:
    """
    Set the expression of an existing variable.

    :param name: The name of the variable to modify.
    :param expression: The new expression to assign to the variable.
                       If None, the expression is cleared.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).expression = expression


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
    return Variable(doc or App.activeDocument(), name).expression


def set_var_group(name: str, group: str, doc: Document | None = None) -> None:
    """
    Set the group of an existing variable.

    :param name: The name of the variable to modify.
    :param group: The new group to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).group = group


def get_var_group(name: str, doc: Document | None = None) -> str:
    """
    Get the group of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The group of the variable.
    """
    return Variable(doc or App.activeDocument(), name).group


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
            read_only=var.read_only,
            hidden=var.hidden,
            sort_key=var.varset.SortKey,
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
                group=var.group,
            )

        if var.value is not None and not var.expression:
            try:
                doc_var.value = var.value
            except Exception:  # noqa: BLE001
                App.Console.PrintError(
                    f"Variable '{var.name}' value ({var.value}) is not valid. (Ignored)\n",
                )

        doc_var.read_only = var.read_only
        doc_var.hidden = var.hidden
        doc_var._set_sort_key(var.sort_key)  # noqa: SLF001

    return True


class Variable:
    """
    A wrapper class for a variable.
    """

    _name: str
    _doc: Document
    _obj: DocumentObject | None = None

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
        self._obj = get_varset(name, doc)

    def create_if_not_exists(
        self,
        *,
        var_type: str = "App::PropertyLength",
        default: Any = None,
        options: VarOptions = None,
        description: str = "",
        expression: str | None = None,
        group: str = "Default",
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
            group=group,
        )
        self._obj = get_varset(self._name, self._doc)
        return self

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Any:
        return self.varset.Value

    @value.setter
    def value(self, value: Any) -> None:
        varset = self.varset
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

    def rename(self, new_name: str, description: str | None = None) -> bool:
        varset = self.varset
        new_name = sanitize_var_name(new_name)
        actual_name = existing_var_name(new_name, self._doc)

        if actual_name and actual_name.lower() != self._name.lower():
            return False

        varset.Label = new_name
        self._name = new_name
        if description:
            varset.setDocumentationOfProperty("Value", description)
            if hasattr(varset, "Description"):
                varset.Description = description
            if hasattr(varset, "Label2"):
                varset.Label2 = description
        self._doc.recompute()
        return True

    @property
    def options(self) -> list[str]:
        return self.varset.getEnumerationsOfProperty("Value") or []

    @options.setter
    def options(self, options: VarOptions) -> None:
        if callable(options):
            options = options()
        if isinstance(options, (list, tuple)):
            self.varset.Value = options
        else:
            msg = "invalid options type, must be list, tuple or callable returning a list"
            raise TypeError(msg)

    @property
    def expression(self) -> str | None:
        if (varset := self.varset) and varset.ExpressionEngine:
            for prop, expr, *_ in varset.ExpressionEngine:
                if prop == "Value":
                    return expr
        return None

    @expression.setter
    def expression(self, expression: str | None) -> None:
        if not expression:
            self.varset.clearExpression("Value")
        self.varset.setExpression("Value", expression)

    def __repr__(self) -> str:
        return f"Variable(name={self.name}, value={self.value})"

    def exists(self) -> bool:
        try:
            return bool(self.varset)
        except ValueError:
            return False

    def delete(self) -> bool:
        try:
            self._doc.removeObject(self.varset.Name)
            self._obj = None
        except ValueError:
            return False
        return True

    @property
    def dependencies(self) -> list[DocumentObject]:
        return list(set(self.varset.OutList)) or []

    @property
    def references(self) -> list[DocumentObject]:
        return list(set(self.varset.InList)) or []

    @property
    def description(self) -> str:
        varset = self.varset
        return (
            getattr(varset, "Description", "")
            or varset.getDocumentationOfProperty("Value")
            or getattr(varset, "Label2", "")
            or ""
        )

    @description.setter
    def description(self, description: str) -> None:
        varset = self.varset
        varset.setDocumentationOfProperty("Value", description)
        if hasattr(varset, "Description"):
            varset.Description = description
        if hasattr(varset, "Label2"):
            varset.Label2 = description

    @property
    def group(self) -> str:
        return self.varset.VarGroup or "Default"

    @group.setter
    def group(self, group: str) -> None:
        self.varset.VarGroup = (group or "Default").title()

    @property
    def var_type(self) -> str:
        return self.varset.getTypeIdOfProperty("Value")

    @property
    def varset(self) -> DocumentObject | None:
        varset = self._obj
        if not varset:
            self._obj = varset = get_varset(self._name, self._doc)
            if not varset:
                msg = f"Variable {self._name} does not exists"
                raise ValueError(msg)
        return varset

    @property
    def internal_name(self) -> str:
        return self.varset.Name

    @property
    def document(self) -> Document:
        return self._doc

    @property
    def editor_mode(self) -> list[str]:
        return self.varset.getEditorMode("Value")

    @editor_mode.setter
    def editor_mode(self, value: str | list[str]) -> None:
        varset = self.varset
        modes = {
            "ReadOnly": (op.or_, 1),
            "Hidden": (op.or_, 2),
            "-ReadOnly": (op.and_, ~1),
            "-Hidden": (op.and_, ~2),
        }
        if not isinstance(value, list):
            value = [value]
        ops = [modes.get(v) for v in varset.getEditorMode("Value")]
        ops.extend(modes.get(v, (op.or_, 0)) for v in value)
        mode = 0
        for f, v in ops:
            mode = f(mode, v)
        varset.setEditorMode("Value", mode)

    @property
    def read_only(self) -> bool:
        return "ReadOnly" in self.editor_mode

    @read_only.setter
    def read_only(self, ro: bool) -> None:
        self.editor_mode = "ReadOnly" if ro else "-ReadOnly"

    @property
    def hidden(self) -> bool:
        try:
            return self.varset.Hidden
        except AttributeError:
            return False

    @hidden.setter
    def hidden(self, value: bool) -> None:
        varset = self.varset
        if not hasattr(varset, "Hidden"):
            varset.addProperty(
                "App::PropertyBool",
                "Hidden",
                "",
                "Hide variable from UI",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.Hidden = value

    @property
    def sort_key(self) -> tuple[str | int, ...]:
        try:
            return (self.group, self.varset.SortKey, self.name)
        except AttributeError:
            return (self.group, 0, self.name)

    def _set_sort_key(self, key: int) -> None:
        varset = self.varset
        if not hasattr(varset, "SortKey"):
            varset.addProperty(
                "App::PropertyInteger",
                "SortKey",
                "",
                "Variable Sort Key",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.SortKey = key

    def reorder(self, delta: float) -> None:
        group = self.group
        group_vars = sorted(v for v in get_vars() if v.group == group)
        for pos, var in enumerate(group_vars):
            var._set_sort_key(pos)  # noqa: SLF001

        seek = self.varset.SortKey + delta
        offset = 0
        ins = -1
        for pos, var in enumerate(v for v in group_vars if v.internal_name != self.internal_name):
            if pos >= seek and offset == 0:
                ins = pos
                offset = 1
            var._set_sort_key(pos + offset)  # noqa: SLF001
        self._set_sort_key(ins if ins > -1 else len(group_vars))

    def __lt__(self, other: Variable) -> bool:
        return self.sort_key < other.sort_key

    def __eq__(self, other: Variable) -> bool:
        if self.exists() and other.exists():
            return self.internal_name == other.internal_name
        return self.name == other.name and self.document == other.document

    @hidden.setter
    def hidden(self, value: bool) -> None:
        varset = self.varset
        if not hasattr(varset, "Hidden"):
            varset.addProperty(
                "App::PropertyBool",
                "Hidden",
                "",
                "Hide variable from UI",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.Hidden = value

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


@dataclass
class VarGroup:
    """Virtual Variables group."""

    doc: Document
    name: str
    sort_key: float = float("inf")
    hidden: bool = False

    def __lt__(self, other: VarGroup) -> bool:
        return self.sort_key < other.sort_key

    def rename(self, new_name: str) -> None:
        new_name = new_name.strip().title()
        for var in get_vars():
            if var.group == self.name:
                var.group = new_name
        self.name = new_name

    def variables(self) -> list[Variable]:
        return sorted([v for v in get_vars(self.doc) if v.group == self.name])


class VarContainer:
    """DocumentObject Group to collect all Vars and manage groups."""

    obj: DocumentObject

    def __init__(self, doc: Document | None = None) -> None:
        self.obj = get_vars_group(doc)
        if "Sort" not in self.obj.PropertiesList:
            self.obj.addProperty("App::PropertyString", "Sort", "", "Group sorting", 2)
        if "Hidden" not in self.obj.PropertiesList:
            self.obj.addProperty("App::PropertyString", "Hidden", "", "Group visibility", 2)

    def groups(self) -> list[VarGroup]:
        names = set(get_groups(self.obj.Document))
        order = {name: pos for pos, name in enumerate(self.obj.Sort.split("\n"))}
        hidden = set(self.obj.Hidden.split("\n"))
        doc = self.obj.Document
        groups = sorted([
            VarGroup(
                doc,
                name,
                order.get(name, float("inf")),
                name in hidden,
            )
            for name in names
        ])
        for i, g in enumerate(groups):
            g.sort_key = i
        return groups

    def reorder(self, names: list[str]) -> None:
        self.obj.Sort = "\n".join(names)

    def set_hidden(self, names: list[str]) -> None:
        self.obj.Hidden = "\n".join(names)


def existing_var_name(name: str, doc: Document | None = None) -> str | None:
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
