# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Properties.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from freecad.vars.utils import get_unique_name
from typing import TYPE_CHECKING, Any
import ast

from freecad.vars.vendor.fcapi import fpo
from FreeCAD import DocumentObject, Document # type: ignore
import contextlib

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from PySide6.QtCore import QObject, Signal

if not TYPE_CHECKING:
    from PySide.QtCore import QObject, Signal


@dataclass
class PropertyTypeInfo:
    """
    Information about a FreeCAD property type.
    """

    name: str
    py_type: type
    editor: str | None = None


def get_all_property_types() -> Generator[tuple[str, PropertyTypeInfo], None, None]:
    for prop in vars(fpo).values():
        if isinstance(prop, fpo._prop_constructor):
            yield (
                prop.prop_type,
                PropertyTypeInfo(
                    prop.prop_type,
                    prop.py_type,
                    get_property_widget(prop.prop_type, prop.py_type),
                ),
            )
    yield (
        "App::PropertyEnumeration",
        PropertyTypeInfo(
            "App::PropertyEnumeration",
            str,
            get_property_widget("App::PropertyEnumeration", str),
        ),
    )


def get_property_widget(name: str, py_type: type) -> str | None:
    match name:
        case "App::PropertyInteger" | "App::PropertyIntegerConstraint":
            return "Gui::IntSpinBox"
        case "App::PropertyFloat" | "App::PropertyFloatConstraint":
            return "Gui::DoubleSpinBox"
        case _ if py_type in (int, float):
            return "Gui::QuantitySpinBox"
    return "Gui::ExpLineEdit"


class PropertyAccessorAdapter(QObject):
    """
    Accessor for FreeCAD property types.
    """

    validation_failed = Signal(DocumentObject, str, object)
    property_assigned = Signal(DocumentObject, str, object)

    def __init__(self, property_type: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.get, self.set = self.accessors(property_type)

    def getter_list(self, obj: DocumentObject, prop: str) -> str:
        data = getattr(obj, prop)
        if not data:
            return "[]"
        return repr(data)

    def setter_list(self, obj: DocumentObject, prop: str, value: Any) -> None:
        try:
            data = ast.literal_eval(value) or []
            if not isinstance(data, list):
                data = [data]
            setattr(obj, prop, data)
            self.property_assigned.emit(obj, prop, data)
        except Exception:  # noqa: BLE001
            self.validation_failed.emit(obj, prop, value)

    def setter_base(self, obj: DocumentObject, prop: str, value: Any) -> None:
        try:
            setattr(obj, prop, value)
            self.property_assigned.emit(obj, prop, value)
        except Exception:  # noqa: BLE001
            self.validation_failed.emit(obj, prop, value)

    def accessors(self, prop_type: str) -> tuple[Callable, Callable]:
        if prop_type in (
            "App::PropertyIntegerList",
            "App::PropertyFloatList",
            "App::PropertyStringList",
        ):
            return self.getter_list, self.setter_list
        return getattr, self.setter_base


@contextlib.contextmanager
def expression_context(doc: Document) -> Generator[Callable[[str], Any], None, None]:
    """
    Creates a temporary evaluation context for expressions within a FreeCAD document.

    This generator function yields an evaluator callable that can be used to evaluate
    expressions in the context of a temporary 'App::VarSet' object added to the given
    document. The temporary object is automatically removed when the context is exited.

    Example:
        with expression_context(doc) as eval_expr:
            result = eval_expr("<<With>>.Value + 2")
    """
    tmp: DocumentObject = doc.addObject("App::VarSet", get_unique_name(doc, "XEval_"))

    def evaluator(expr: str) -> Any:
        try:
            return tmp.evalExpression(expr)
        except Exception as e:
            msg = f"Error evaluating expression '{expr}': {e}"
            raise RuntimeError(msg) from e

    try:
        yield evaluator
    finally:
        doc.removeObject(tmp.Name)

@cache
def get_supported_property_types() -> dict[str, str]:
    """
    Get the supported property types for the variable editor.

    :return: A dict of supported property types.
    """

    def basic_types() -> Generator[tuple[str, str], None, None]:
        for prop, info in PROPERTY_INFO.items():
            if info.py_type in (int, float, str):
                yield prop, prop
                if f"{prop}List" in PROPERTY_INFO:
                    yield f"{prop}List", f"{prop}List"
        yield "App::PropertyEnumeration", "App::PropertyEnumeration"

    return dict(basic_types())


PROPERTY_INFO = dict(get_all_property_types())
