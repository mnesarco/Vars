# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Editors UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from freecad.vars.vendor.fcapi.events import events
from freecad.vars.vendor.fcapi.lang import dtr
from freecad.vars.vendor.fcapi import fcui as ui
from freecad.vars.api import (
    Variable,
    get_vars,
    get_groups,
    create_var,
    export_variables,
    import_variables,
)
from freecad.vars.core.properties import (
    PROPERTY_INFO,
    PropertyAccessorAdapter,
    get_supported_property_types,
)
from itertools import groupby
from freecad.vars.config import preferences, resources
from .style import FlatIcon, interpolate_style_vars, TEXT_COLOR
from textwrap import shorten, dedent
import contextlib
from . import widgets as uix

import FreeCAD as App

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Generator
    from FreeCAD import Document, DocumentObject  # type: ignore
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QCompleter
    from PySide6.QtCore import QSettings

if not TYPE_CHECKING:
    from PySide.QtGui import QGraphicsOpacityEffect, QCompleter
    from PySide.QtCore import QSettings

style_vars = {
    "border_color": TEXT_COLOR,
}

stylesheet = interpolate_style_vars(
    """
    QFrame[varEditorFocus="off"] {
        border: 1px transparent;
        border-radius: 0px;
        margin: 0px;
    }

    QFrame[varEditorFocus="on"] {
        border-radius: 0px;
        border: 1px transparent;
        border-left: 1px solid {border_color};
        border-right: 1px solid {border_color};
        margin: 0px;
    }

    """,
    style_vars,
)


def set_visibility(widget: ui.QWidget, visibility: bool) -> None:
    """
    Set the visibility of the widget using height to avoid widget destroy.

    If visibility is True, the widget height is set to the size hint.
    If visibility is False, the widget height is set to 0.

    :param widget: The widget to set the visibility for.
    :param visibility: The visibility of the widget.
    """
    if visibility:
        widget.setFixedHeight(widget.sizeHint().height())
        widget.setEnabled(True)
    else:
        widget.setFixedHeight(0)
        widget.setEnabled(False)


def is_visible(widget: ui.QWidget) -> bool:
    """
    Determine if a widget is visible based on its height.

    A widget is considered visible if its height is greater than zero.

    :param widget: The widget to check for visibility.
    :return: True if the widget is visible, False otherwise.
    """
    return widget.size().height() > 0


def add_action(
    parent: ui.QWidget | ui.QActionGroup,
    *,
    text: str | None = "",
    icon: str | None = None,
    tooltip: str | None = None,
    shortcut: str | None = None,
    receiver: Callable[[], None] | None = None,
) -> ui.QAction:
    """
    Add a QAction to the widget.

    :param widget: The widget to add the action to.
    :param text: The text to set for the action. Defaults to an empty string.
    :param icon: The icon name to set for the action. Defaults to None.
    :param tooltip: The tooltip to set for the action. Defaults to None.
    :param shortcut: The shortcut to set for the action. Defaults to None.
    :param receiver: The function to connect to the action's triggered signal. Defaults to None.
    """
    action = ui.QAction(str(text), parent)
    if icon:
        action.setIcon(FlatIcon(resources.icon(icon)))
    if tooltip:
        action.setToolTip(str(tooltip))
    if shortcut:
        action.setShortcut(shortcut)
    if receiver:
        action.triggered.connect(receiver)
    parent.addAction(action)
    return action


class VarEditor(ui.QObject):
    """Variable editor row."""

    variable: Variable
    label: ui.InputTextWidget
    description: ui.QLabel
    editor: ui.InputQuantityWidget
    widget: ui.QWidget
    event_bus: EventBus

    def __init__(
        self,
        variable: Variable,
        event_bus: EventBus,
        add: bool = True,
        parent: ui.QObject | None = None,
    ) -> None:
        """
        Initialize a variable editor.

        :param variable: The variable to edit.
        :raises ValueError: If the variable does not exist.
        """
        super().__init__(parent)
        if not variable.exists():
            msg = f"Variable {variable.name} not found"
            raise ValueError(msg)

        self.variable = variable
        self.event_bus = event_bus
        self.description_visible = bool(preferences.show_descriptions() and variable.description)

        with ui.Container(
            contentsMargins=(0, 0, 0, 0),
            properties={"varEditorFocus": "off"},
            add=add,
            q_widget=ui.QFrame,
        ) as box:
            self.widget = box
            self.setParent(box)
            box.varInstance = self
            tooltip = self.var_tooltip()
            with ui.Col(contentsMargins=(2, 0, 2, 0), spacing=0):
                with ui.Row(contentsMargins=(0, 0, 0, 0), spacing=0):
                    self.label = ui.InputText(
                        variable.name,
                        readOnly=True,
                        focusPolicy=ui.Qt.FocusPolicy.ClickFocus,
                        stretch=45,
                        styleSheet="font-weight: bold;",
                        toolTip=tooltip,
                        cursorPosition=0,
                    )
                    self.create_input_editor(tooltip)
                    self.create_menu()

            self.create_description(box)
            self.install_focus_style_listener(box)

        event_bus.var_deleted.connect(self.remove_self)

    def remove_self(self, var: Variable) -> None:
        """Notify the group to remove this editor."""
        if var.name == self.variable.name:
            self.event_bus.remove_var_editor.emit(self)

    def install_focus_style_listener(self, parent: ui.QWidget) -> None:
        ui.QApplication.instance().focusChanged.connect(self.on_focus_change)

    def create_description(self, parent: ui.QWidget) -> None:
        opacity = QGraphicsOpacityEffect(parent, opacity=0.5)
        with ui.Container(contentsMargins=(0, 0, 0, 0), visible=self.description_visible):
            with ui.Row(contentsMargins=(1, 0, 0, 5), spacing=0):
                self.desc_icon = ui.IconLabel(
                    icon=FlatIcon(resources.icon("child-arrow.svg")),
                    graphicsEffect=opacity,
                    styleSheet="margin-left: 5px;",
                    alignment=ui.Qt.AlignmentFlag.AlignTop,
                )
                self.description = ui.TextLabel(
                    shorten(self.variable.description, 160, placeholder=" ..."),
                    sizePolicy=(
                        ui.QSizePolicy.Policy.Preferred,
                        ui.QSizePolicy.Policy.MinimumExpanding,
                    ),
                    wordWrap=True,
                    graphicsEffect=opacity,
                    stretch=1,
                    styleSheet="padding-left: 5px; padding-top: 5px;",
                )

    def create_input_editor(self, tooltip: str) -> ui.QWidget:
        variable = self.variable
        if prop_info := PROPERTY_INFO.get(variable.var_type):
            widget_type = prop_info.editor
        else:
            widget_type = "Gui::ExpLineEdit"

        accessor_adapter = PropertyAccessorAdapter(variable.var_type)
        accessor_adapter.validation_failed.connect(self.on_validation_failed)
        accessor_adapter.property_assigned.connect(self.on_property_assigned)

        if variable.var_type == "App::PropertyEnumeration":
            self.editor = uix.PropertyEnumerationWidget(
                obj=variable.varset,
                prop_name="Value",
                accessor_adapter=accessor_adapter,
                objectName=f"VarEditor_{variable.internal_name}",
                stretch=55,
            )
        else:
            self.editor = ui.InputQuantity(
                obj=variable.varset,
                property="Value",
                auto_apply=True,
                stretch=55,
                widget_type=widget_type,
                name=f"VarEditor_{variable.internal_name}",
                toolTip=tooltip,
                accessor_adapter=accessor_adapter,
            )

        self.label.forwardFocusTo = self.editor
        self.editor.setValue(variable.value)
        self.editor.valueChanged.connect(
            lambda _: self.event_bus.variable_changed.emit(variable),
        )

        self.event_bus.variable_changed.connect(self.silent_value_update)
        self.event_bus.var_renamed.connect(self.ui_update)

        return self.editor

    def on_validation_failed(self, _obj: DocumentObject, _prop: str, _value: object) -> None:
        if getattr(self.label, "_warning", None):
            return
        action = ui.QAction(
            icon=FlatIcon(resources.icon("warning.svg")),
            toolTip=str(dtr("Vars", "Invalid value")),
        )
        self.label.addAction(action, ui.QLineEdit.ActionPosition.TrailingPosition)
        self.label._warning = action  # noqa: SLF001

    def on_property_assigned(self, _obj: DocumentObject, _prop: str, _value: object) -> None:
        if action := getattr(self.label, "_warning", None):
            self.label.removeAction(action)
            del self.label._warning  # noqa: SLF001

    def ui_update(self, var: Variable) -> None:
        if var.name == self.variable.name:
            self.label.setText(var.name)
            self.label.setToolTip(self.var_tooltip())
            self.description.setText(var.description)
            self.silent_value_update(var)

    def silent_value_update(self, var: Variable) -> None:
        if var.name != self.variable.name:
            self.editor.blockSignals(True)
            self.editor.setValue(self.variable.value)
            self.editor.blockSignals(False)

    def var_tooltip(self) -> str:
        return dedent(f"""
            <p>{self.variable.name}: {shorten(self.variable.description, 255, placeholder="...")}</p>
            <pre>Type: {self.variable.var_type}
            Expression: &lt;&lt;{self.variable.name}&gt;&gt;.Value
            Python: freecad.vars.api.get_var("{self.variable.name}", doc)</pre>
            """)

    def create_menu(self) -> None:
        button = ui.Button(
            text="...",
            tool=True,
            popupMode=ui.QToolButton.ToolButtonPopupMode.InstantPopup,
            arrowType=ui.Qt.ArrowType.NoArrow,
            toolButtonStyle=ui.Qt.ToolButtonStyle.ToolButtonTextOnly,
            styleSheet="QToolButton::menu-indicator { image: none; }",
            focusPolicy=ui.Qt.FocusPolicy.NoFocus,
        )

        add_action(
            button,
            text=dtr("Vars", "Rename"),
            receiver=self.cmd_rename,
            icon="rename.svg",
        )

        add_action(
            button,
            text=dtr("Vars", "Show references"),
            receiver=self.cmd_references,
            icon="reference.svg",
        )

        add_action(
            button,
            text=dtr("Vars", "Change definition"),
            receiver=self.cmd_edit,
            icon="edit.svg",
        )

        add_action(
            button,
            text=dtr("Vars", "Delete"),
            receiver=self.cmd_delete,
            icon="delete.svg",
        )

    def filter(self, text: str) -> None:
        if not text or text.lower() in self.variable.name.lower():
            set_visibility(self.widget, True)
            return
        set_visibility(self.widget, False)

    def cmd_rename(self) -> None:
        self.event_bus.goto_rename_var.emit(self.variable)

    def cmd_references(self) -> None:
        self.event_bus.goto_var_references.emit(self.variable)

    def cmd_edit(self) -> None:
        self.event_bus.goto_edit_var.emit(self.variable)

    def cmd_delete(self) -> None:
        self.event_bus.goto_delete_var.emit(self.variable)

    def on_focus_change(self, old: ui.QWidget, new: ui.QWidget) -> None:
        is_parent_of_old = old and self.widget.isAncestorOf(old)
        is_parent_of_new = new and self.widget.isAncestorOf(new)

        if not (is_parent_of_old and is_parent_of_new):
            if is_parent_of_old:
                parent = self.widget
                parent.setProperty("varEditorFocus", "off")
                parent.style().unpolish(parent)
                parent.style().polish(parent)
            elif is_parent_of_new:
                parent = self.widget
                parent.setProperty("varEditorFocus", "on")
                parent.style().unpolish(parent)
                parent.style().polish(parent)

        if next_widget := getattr(new, "forwardFocusTo", None):
            next_widget.setFocus()


class EventBus(ui.QObject):
    """Event bus for async inter-object communication."""

    goto_home = ui.Signal()
    goto_create_var = ui.Signal()
    goto_edit_var = ui.Signal(Variable)
    goto_rename_var = ui.Signal(Variable)
    goto_delete_var = ui.Signal(Variable)
    goto_var_references = ui.Signal(Variable)

    variable_changed = ui.Signal(Variable)

    var_renamed = ui.Signal(Variable)
    var_deleted = ui.Signal(Variable)
    var_created = ui.Signal(Variable)
    var_edited = ui.Signal(Variable)

    request_focus = ui.Signal(str)

    remove_var_editor = ui.Signal(VarEditor)

    reload_vars = ui.Signal()

    def __init__(self, *args) -> None:  # noqa: D107
        super().__init__(*args)


class VarGroupSection(ui.QObject):
    """Variable group section."""

    name: str
    editors: list[VarEditor]
    container: ui.QWidget
    editors_layout: ui.QLayout
    event_bus: EventBus

    def __init__(
        self,
        name: str,
        variables: list[Variable],
        event_bus: EventBus,
        add: bool = True,
        parent: ui.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.event_bus = event_bus

        with ui.GroupBox(
            title=name,
            contentsMargins=(2, 2, 2, 2),
            objectName=f"VarsGroupBox{hash(name)}",
            add=add,
        ) as box:
            self.container = box
            box.groupInstance = self
            with ui.Col(contentsMargins=(2, 2, 2, 2), spacing=0) as col:
                self.editors_layout = col.layout()
                self.editors = [
                    VarEditor(var, event_bus, parent=self) for var in variables if var.group == name
                ]

        event_bus.remove_var_editor.connect(self.remove_var_editor)

    def remove_var_editor(self, editor: VarEditor) -> None:
        if editor in self.editors:
            self.editors_layout.removeWidget(editor.widget)
            self.editors.remove(editor)
            editor.widget.deleteLater()
            editor.deleteLater()

    def filter(self, text: str) -> None:
        visible = False
        for editor in self.editors:
            editor.filter(text)
            visible = visible or is_visible(editor.widget)
        set_visibility(self.container, visible)

    def add_variable_editor(self, var: Variable) -> None:
        if var.group == self.name:
            ui.build_context().reset()
            editor = VarEditor(var, self.event_bus, add=False, parent=self)
            self.editors.append(editor)
            self.editors_layout.addWidget(editor.widget)
            ui.build_context().reset()
            ui.QApplication.instance().processEvents()
            self.event_bus.request_focus.emit(editor.editor.objectName())


def toolbar_button(
    icon: str,
    tooltip: str,
    callback: Callable[[], None],
    shortcut: str | None = None,
) -> ui.Button:
    """
    Create a toolbar button.

    :param icon: The icon name to set for the button.
    :param tooltip: The tooltip to set for the button.
    :param callback: The function to connect to the button's clicked signal.
    :param default: If True, the button will be set as default.
    :return: The created button.
    """
    return ui.Button(
        icon=FlatIcon(resources.icon(icon)),
        tool=True,
        toolButtonStyle=ui.Qt.ToolButtonStyle.ToolButtonIconOnly,
        focusPolicy=ui.Qt.FocusPolicy.NoFocus,
        clicked=callback,
        toolTip=str(tooltip),
        shortcut=shortcut,
    )


@contextlib.contextmanager
def ToolBar(*, stretch: bool = True) -> Generator[ui.QWidget, None, None]:
    with ui.Row(contentsMargins=(0, 0, 0, 0), spacing=0) as row:
        yield row
        if stretch:
            ui.Stretch(1)


class UIPage(ui.QObject):
    """View: Base class for pages."""

    editor: VariablesEditor
    page_id: int
    event_bus: EventBus
    dialog: ui.QWidget
    doc: Document

    def __init__(self, editor: VariablesEditor, parent: ui.QObject | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.page_id = editor.pages.count()
        self.event_bus = editor.event_bus
        self.dialog = editor.dialog
        self.doc = editor.doc


class HomePage(UIPage):
    """View: Home page."""

    scroll: ui.QScrollArea
    auto_recompute: bool
    recompute_btn: ui.QAbstractButton

    def __init__(
        self,
        editor: VariablesEditor,
        groups: list[tuple[str, list[Variable]]],
        parent: ui.QObject | None = None,
    ) -> None:
        super().__init__(editor, parent)
        self.auto_recompute = False
        with ui.Col():
            self.toolbar()
            editor.search = self.search_box()
            with (
                ui.Scroll(widgetResizable=True) as scroll,
                ui.Container(),
                ui.Col(contentsMargins=(0, 0, 0, 0), spacing=0),
            ):
                bus = self.event_bus
                self.create_sections(groups)
                ui.Stretch(1)

                self.scroll = scroll
                bus.request_focus.connect(self.on_request_focus)

        self.event_bus.variable_changed.connect(self.recompute)
        self.event_bus.reload_vars.connect(self.reload_content)

    def recompute(self, var: Variable) -> None:
        if self.auto_recompute:
            var.doc.recompute()

    def create_sections(self, groups: list[tuple[str, list[Variable]]], add: bool = True) -> None:
        with ui.Col(spacing=10, add=add) as col:
            col.setObjectName("_VarsEditorHomeContent_")
            bus = self.event_bus
            self.editor.sections_layout = col.layout()
            self.editor.sections = [
                VarGroupSection(name, items, bus, parent=self) for name, items in groups
            ]
        return col

    def reload_content(self) -> None:
        self.dialog.close()
        if doc := App.activeDocument():
            VariablesEditor(doc)

    def on_request_focus(self, name: str) -> None:
        def task() -> None:
            if widget := self.dialog.findChild(ui.QWidget, name):
                if self.scroll.isAncestorOf(widget):
                    self.scroll.ensureWidgetVisible(widget.parent())
                widget.setFocus()
        ui.QTimer.singleShot(100, task)

    def search_box(self) -> ui.QWidget:
        with ui.Row(contentsMargins=(0, 0, 0, 0)) as row:
            search = ui.InputText(placeholderText=str(dtr("Vars", "Search...")), stretch=1)
            search.textChanged.connect(self.editor.cmd_filter)
            return row

    def toolbar(self) -> ui.QWidget:
        editor = self.editor
        with ToolBar(stretch=False) as row:
            toolbar_button(
                icon="add.svg",
                tooltip=dtr("Vars", "Create new variable"),
                callback=editor.cmd_create_var,
            )
            toolbar_button(
                icon="file-import.svg",
                tooltip=str(dtr("Vars", "Import variables")),
                callback=editor.cmd_import,
            )
            toolbar_button(
                icon="file-export.svg",
                tooltip=str(dtr("Vars", "Export variables")),
                callback=editor.cmd_export,
            )
            toolbar_button(
                icon="table.svg",
                tooltip=str(dtr("Vars", "Generate report table")),
                callback=editor.cmd_report,
            )
            ui.Stretch(1)

            pause_icon = "recompute-pause.svg"
            auto_icon = "recompute-run.svg"
            pause_tooltip = dtr("Vars", "Pause automatic recomputation<hr />Currently Automatic")
            auto_tooltip = dtr("Vars", "Enable automatic recomputation<hr />Currently Paused")

            self.recompute_btn = toolbar_button(
                icon=pause_icon if self.auto_recompute else auto_icon,
                tooltip=str(pause_tooltip) if self.auto_recompute else str(auto_tooltip),
                callback=lambda: self.toggle_auto_recompute(
                    pause_icon,
                    pause_tooltip,
                    auto_icon,
                    auto_tooltip,
                ),
            )
        return row

    def toggle_auto_recompute(
        self, pause_icon: str, pause_tooltip: dtr, auto_icon: str, auto_tooltip: dtr
    ) -> None:
        self.auto_recompute = not self.auto_recompute
        if self.auto_recompute:
            icon = pause_icon
            tooltip = str(pause_tooltip)
            self.doc.recompute()
        else:
            icon = auto_icon
            tooltip = str(auto_tooltip)
        self.recompute_btn.setIcon(FlatIcon(resources.icon(icon)))
        self.recompute_btn.setToolTip(tooltip)


class VarReferencesPage(UIPage):
    """View: Show references page."""

    references: ReferencesTable
    name: ui.InputTextWidget
    description: ui.QLabel

    def __init__(self, editor: VariablesEditor, parent: ui.QObject | None = None) -> None:
        super().__init__(editor, parent)
        with ui.Col():
            with ToolBar():
                toolbar_button(
                    icon="arrow-back.svg",
                    tooltip=str(dtr("Vars", "Cancel")),
                    callback=self.on_cancel,
                )

            with ui.GroupBox(title=str(dtr("Vars", "References"))):
                ui.TextLabel(str(dtr("Vars", "Variable Name:")))
                self.name = ui.InputText(value="", readOnly=True)
                self.description = ui.TextLabel(
                    text="",
                    wordWrap=True,
                    styleSheet="padding: 5px;",
                )
                self.references = ReferencesTable(str(dtr("Vars", "Known References:")))
            ui.Stretch(1)

    def set_var(self, var: Variable) -> None:
        self.references.update(var)
        self.description.setText(var.description or "")
        self.name.setText(var.name)

    def on_cancel(self) -> None:
        self.editor.event_bus.goto_home.emit()


class VarEditPage(UIPage):
    """View: Edit variable form page."""

    var: Variable | None = None
    description: ui.InputTextMultilineWidget
    name: ui.InputTextWidget
    types: ui.InputOptionsWidget
    groups: ui.InputOptionsWidget
    root: ui.QGroupBox
    messages: ui.QLabel
    references: ReferencesTable
    options: ui.InputTextMultilineWidget

    def __init__(self, editor: VariablesEditor, parent: ui.QObject | None = None) -> None:
        super().__init__(editor, parent)
        with ui.Col():
            with ToolBar():
                toolbar_button(
                    icon="arrow-back.svg",
                    tooltip=str(dtr("Vars", "Cancel")),
                    callback=self.on_cancel,
                )
                toolbar_button(
                    icon="check-mark.svg",
                    tooltip=str(dtr("Vars", "Save")),
                    callback=self.on_save,
                )

            with (
                ui.GroupBox(
                    title=str(dtr("Vars", "Edit variable")),
                    contentsMargins=(0, 0, 0, 0),
                ) as root,
                ui.Col(contentsMargins=(0, 0, 0, 0)),
                ui.Scroll(widgetResizable=True, contentsMargins=(0, 0, 0, 0)),
                ui.Container(),
            ):
                self.root = root
                with ui.Col():
                    ui.TextLabel(str(dtr("Vars", "Name:")))
                    self.name = ui.InputText(value="")

                    ui.TextLabel(str(dtr("Vars", "Type:")))
                    self.types = ui.InputOptions(
                        get_supported_property_types(),
                        editable=True,
                        insertPolicy=ui.QComboBox.InsertPolicy.NoInsert,
                    )

                    ui.TextLabel(str(dtr("Vars", "Group:")))
                    self.groups = ui.InputOptions(
                        {v: v for v in get_groups()},
                        editable=True,
                        insertPolicy=ui.QComboBox.InsertPolicy.InsertAtBottom,
                    )

                    for completer in (self.groups.completer(), self.types.completer()):
                        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                        completer.setFilterMode(ui.Qt.MatchFlag.MatchContains)

                    ui.TextLabel(str(dtr("Vars", "Description:")))
                    self.description = ui.InputTextMultiline(
                        value="",
                        minimumHeight=64,
                        maximumHeight=100,
                        max_length=256,
                        stretch=1,
                    )

                    with ui.Col(contentsMargins=(0, 0, 0, 0)):
                        ui.TextLabel(str(dtr("Vars", "Options:")))
                        self.options = ui.InputTextMultiline(
                            value="",
                            minimumHeight=64,
                            maximumHeight=100,
                            max_length=256,
                            stretch=1,
                        )

                    self.types.editTextChanged.connect(
                        lambda text: set_visibility(
                            self.options.parent(),
                            text == "App::PropertyEnumeration",
                        ),
                    )

                    self.references = ReferencesTable(
                        str(dtr("Vars", "Known References (May Break)")),
                    )

                    ui.Stretch(1)
            self.messages = ui.TextLabel(visible=False, wordWrap=True)

    def init_new(self) -> None:
        self.var = None
        self.root.setTitle(str(dtr("Vars", "Create new variable")))
        self.name.setText("")
        self.name.setEnabled(True)
        self.description.setText("")
        self.messages.setText("")
        self.messages.hide()
        self.types.setValue(preferences.default_property_type())
        self.groups.setOptions({v: v for v in get_groups()})
        self.options.setText("")
        self.references.table.parent().hide()

    def init_edit(self, var: Variable) -> None:
        self.var = var
        self.root.setTitle(str(dtr("Vars", "Edit variable")))
        self.name.setText(var.name)
        self.name.setEnabled(False)
        self.description.setText(var.description)
        self.types.setValue(var.var_type)
        if options := var.options:
            self.options.setText("\n".join(str(opt) for opt in options))
        self.groups.setOptions({v: v for v in get_groups()})
        self.groups.setValue(var.group)
        self.references.update(var)
        self.messages.setText("")
        self.messages.hide()

    def on_cancel(self) -> None:
        self.event_bus.goto_home.emit()

    def on_save(self) -> None:
        self.messages.hide()
        var_type = (self.types.currentText() or "").strip()
        var_group = (self.groups.currentText() or "Default").strip()

        if var_type not in PROPERTY_INFO:
            self.messages.setText(
                str(dtr("Vars", "Invalid property type selected.")),
            )
            self.messages.show()
            return

        if options := self.options.value().strip():
            options = options.splitlines()
        else:
            options = None

        if self.var is None and (
            err := self.editor.do_create_var(
                name=self.name.text().strip(),
                var_type=var_type,
                group=var_group,
                description=self.description.value().strip(),
                options=options,
            )
        ):
            self.messages.setText(err)
            self.messages.show()
            return

        if self.var is not None and (
            err := self.editor.do_edit_var(
                self.var,
                var_type=var_type,
                group=var_group,
                description=self.description.value().strip(),
                options=options,
            )
        ):
            self.messages.setText(err)
            self.messages.show()
            return


class ReferencesTable:
    """View: References Table Widget."""

    table: ui.TableWidget

    def __init__(self, title: str) -> None:
        with ui.Col(contentsMargins=(0, 0, 0, 0)):
            ui.TextLabel(title)
            self.table = ui.Table(
                headers=[
                    str(dtr("Vars", "Object Label")),
                    str(dtr("Vars", "Property")),
                    str(dtr("Vars", "Expression")),
                    str(dtr("Vars", "Internal Name")),
                ],
                rows=[],
                stretch=1,
                minimumHeight=100,
            )

    def update(self, var: Variable) -> bool:
        refs = sorted(self.get_references(var), key=lambda x: x[0])
        if refs:
            self.table.setRowsData(refs)
            self.table.parent().show()
            self.table.resizeColumnsToContents()
            return True

        self.table.parent().hide()
        self.table.setRowsData([])
        return False

    def get_references(self, var: Variable) -> Generator[list[str], None, None]:
        name, int_name = f"<<{var.name}>>", var.internal_name
        for obj in var.references:
            if obj.Name == "XVarGroup":
                continue
            for prop, expr in obj.ExpressionEngine:
                if name in expr or int_name in expr:
                    yield [f"{obj.Label}", prop, expr, obj.Name]


class VarRenamePage(UIPage):
    """View: Rename variable form page."""

    old: ui.InputTextWidget
    new: ui.InputTextWidget
    var: Variable
    message: ui.QLabel
    references: ReferencesTable

    def __init__(self, editor: VariablesEditor, parent: ui.QObject | None = None) -> None:
        super().__init__(editor, parent)
        self.var = None
        with ui.Col():
            with ToolBar():
                toolbar_button(
                    icon="arrow-back.svg",
                    tooltip=str(dtr("Vars", "Cancel")),
                    callback=self.on_cancel,
                )
                toolbar_button(
                    icon="check-mark.svg",
                    tooltip=str(dtr("Vars", "Rename")),
                    callback=self.on_rename,
                )

            with ui.GroupBox(title=str(dtr("Vars", "Rename variable"))):
                with ui.Col():
                    self.old = ui.InputText(
                        value="",
                        label=str(dtr("Vars", "Old name:")),
                        enabled=False,
                    )
                    self.new = ui.InputText(
                        value="",
                        label=str(dtr("Vars", "New name:")),
                    )
                    ui.TextLabel(
                        str(
                            dtr(
                                "Vars",
                                (
                                    "Renaming variables may break "
                                    "references from external files "
                                    "or python scripts."
                                ),
                            ),
                        ),
                        wordWrap=True,
                        styleSheet="padding: 5px;",
                    )

                    self.references = ReferencesTable(
                        str(dtr("Vars", "Known References (Auto update)")),
                    )

                    ui.Stretch(1)
                    self.message = ui.TextLabel("", wordWrap=True)

    def on_cancel(self) -> None:
        self.event_bus.goto_home.emit()

    def on_rename(self) -> None:
        name = self.new.text().strip()
        self.message.setText("")
        if err := self.editor.do_rename_var(self.var, name):
            self.message.setText(err)
            self.message.show()

    def set_var(self, var: Variable) -> None:
        self.var = var
        self.message.setText("")
        self.old.setText(var.name)
        self.new.setText(var.name)
        self.references.update(var)


class VarDeletePage(UIPage):
    """View: Delete variable form page."""

    name: ui.InputTextWidget
    var: Variable
    message: ui.QLabel
    references: ReferencesTable
    confirm: ui.QCheckBox
    button: ui.QPushButton

    def __init__(self, editor: VariablesEditor, parent: ui.QObject | None = None) -> None:
        super().__init__(editor, parent)
        self.var = None
        with ui.Col():
            with ToolBar():
                toolbar_button(
                    icon="arrow-back.svg",
                    tooltip=str(dtr("Vars", "Cancel")),
                    callback=self.on_cancel,
                )

            with ui.GroupBox(title=str(dtr("Vars", "Delete variable"))):
                with ui.Col():
                    self.name = ui.InputText(
                        value="",
                        label=str(dtr("Vars", "Name:")),
                        readOnly=True,
                    )
                    ui.TextLabel(
                        str(
                            dtr(
                                "Vars",
                                "Deleting variables will break all references to it. This action is irreversible.",
                            ),
                        ),
                        wordWrap=True,
                        styleSheet="padding: 5px;",
                    )

                    with ui.GroupBox(title=str(dtr("Vars", "Danger zone"))), ui.Col():
                        with ui.Row():
                            ui.TextLabel(
                                str(dtr("Vars", "Confirm deletion:")),
                            )
                            self.confirm = ui.InputBoolean()
                            ui.Stretch(1)

                        self.button = ui.Button(
                            label=str(dtr("Vars", "Delete")),
                            icon=FlatIcon(resources.icon("delete.svg")),
                            clicked=self.on_delete,
                            enabled=False,
                        )

                        self.confirm.toggled.connect(
                            lambda checked: self.button.setEnabled(checked),
                        )

                    self.references = ReferencesTable(
                        str(dtr("Vars", "Known References (Will break)")),
                    )

                    ui.Stretch(1)
                    self.message = ui.TextLabel("", wordWrap=True)

    def on_cancel(self) -> None:
        self.event_bus.goto_home.emit()

    def on_delete(self) -> None:
        if err := self.editor.do_delete_var(self.var):
            self.message.setText(err)
            self.message.show()

    def set_var(self, var: Variable) -> None:
        self.var = var
        self.confirm.setChecked(False)
        self.button.setText(str(dtr("Vars", "Delete {name}")).format(name=var.name))
        self.message.setText("")
        self.name.setText(var.name)
        self.references.update(var)


class VariablesEditor(ui.QObject):
    """Controller: Variables Editor."""

    doc: Document
    sections: list[VarGroupSection]
    sections_layout: ui.QLayout
    dialog: ui.QWidget
    search: ui.InputTextWidget
    pages: ui.QStackedLayout
    event_bus: EventBus

    edit_page: VarEditPage
    rename_page: VarRenamePage
    references_page: VarReferencesPage
    delete_page: VarDeletePage
    home_page: HomePage

    q_settings = QSettings("FreeCAD", "mnesarco-Vars")

    def __init__(self, doc: Document) -> None:
        super().__init__()
        self.doc = doc
        groups = self.get_groups()

        with ui.Dialog(
            title=str(dtr("Vars", "Variables")), styleSheet=stylesheet, modal=False
        ) as dialog:
            dialog.setAttribute(ui.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.dialog = dialog
            self.event_bus = EventBus(self)
            self.setParent(dialog)
            with ui.Stack() as pages:
                self.pages = pages.layout()
                self.home_page = HomePage(self, groups, dialog)
                self.edit_page = VarEditPage(self, dialog)
                self.rename_page = VarRenamePage(self, dialog)
                self.references_page = VarReferencesPage(self, dialog)
                self.delete_page = VarDeletePage(self, dialog)

            x, y, w, h = self.get_geometry()
            if w and h:
                dialog.resize(w, h)
            if x or y:
                dialog.move(x, y)

        self.init_events()

        @events.document.activated
        def on_document_activate(event: events.DocumentEvent) -> None:
            if event.doc != self.doc:
                on_document_activate.unsubscribe()
                with contextlib.suppress(Exception):
                    dialog.close() # TODO: Investigate lifecycle issue

        dialog.onMove.connect(self.on_move_or_resize)
        dialog.onResize.connect(self.on_move_or_resize)


    def get_geometry(self) -> tuple[int, int, int, int]:
        x = self.q_settings.value("x", 0, int)
        y = self.q_settings.value("y", 0, int)
        w = self.q_settings.value("w", 800, int)
        h = self.q_settings.value("h", 600, int)
        return x, y, w, h


    def on_move_or_resize(self, _e) -> None:
        pos = self.dialog.pos()
        size = self.dialog.size()
        self.q_settings.setValue("x", pos.x())
        self.q_settings.setValue("y", pos.y())
        self.q_settings.setValue("w", size.width())
        self.q_settings.setValue("h", size.height())

    def get_groups(self) -> dict[str, list[Variable]]:
        supported_types = get_supported_property_types()
        variables = [v for v in get_vars(self.doc) if v.var_type in supported_types]
        return groupby(sorted(variables, key=lambda v: v.group), lambda v: v.group)

    def init_events(self) -> None:
        bus = self.event_bus
        bus.goto_edit_var.connect(self.cmd_edit_var)
        bus.goto_rename_var.connect(self.cmd_rename_var)
        bus.goto_home.connect(self.on_home)
        bus.var_created.connect(self.on_var_created)
        bus.goto_var_references.connect(self.cmd_var_references)
        bus.goto_delete_var.connect(self.cmd_delete_var)
        bus.var_edited.connect(self.on_var_edited)

    def cmd_var_references(self, var: Variable) -> None:
        self.references_page.set_var(var)
        self.switch_to_page(self.references_page)

    def cmd_delete_var(self, var: Variable) -> None:
        self.delete_page.set_var(var)
        self.switch_to_page(self.delete_page)

    def on_var_created(self, var: Variable) -> None:
        for section in self.sections:
            if section.name == var.group:
                section.add_variable_editor(var)
                break
        else:
            ui.build_context().reset()
            new_section = VarGroupSection(
                var.group, [var], self.event_bus, add=False, parent=self.dialog
            )
            self.sections.append(new_section)
            self.sections_layout.addWidget(new_section.container)
            ui.build_context().reset()
            ui.QApplication.instance().processEvents()
            self.event_bus.request_focus.emit(new_section.editors[0].editor.objectName())

    def on_home(self) -> None:
        self.switch_to_page(self.home_page)

    def cmd_rename_var(self, var: Variable) -> None:
        self.rename_page.set_var(var)
        self.switch_to_page(self.rename_page)

    def cmd_filter(self, text: str) -> None:
        for section in self.sections:
            section.filter(text)

    def cmd_import(self) -> None:
        file = ui.get_open_file(
            caption=str(dtr("Vars", "Import variables")),
            filter=str(dtr("Vars", "Variables files (*.fcvars)")),
        )

        if file and import_variables(file, self.doc):
            self.event_bus.reload_vars.emit()

    def cmd_export(self) -> None:
        file = ui.get_save_file(
            caption=str(dtr("Vars", "Export variables")),
            filter=str(dtr("Vars", "Variables files (*.fcvars)")),
            file=f"{self.doc.Name}.fcvars",
        )

        if file:
            export_variables(file, self.doc)

    def cmd_report(self) -> None:
        file = ui.get_save_file(
            caption=str(dtr("Vars", "Export variables report html")),
            filter=str(dtr("Vars", "Html (*.html)")),
            file=f"{self.doc.Name}.html",
        )
        if file:
            from freecad.vars.ui.report import report_vars

            report_vars(file, self.doc)

    def switch_to_page(self, page: UIPage) -> None:
        self.pages.setCurrentIndex(page.page_id)

    def cmd_create_var(self) -> None:
        self.edit_page.init_new()
        self.switch_to_page(self.edit_page)

    def cmd_edit_var(self, var: Variable) -> None:
        self.edit_page.init_edit(var)
        self.switch_to_page(self.edit_page)

    def do_create_var(
        self,
        name: str,
        var_type: str,
        group: str,
        description: str,
        options: list[str] | None,
    ) -> str | None:
        try:
            var = create_var(
                name=name,
                var_type=var_type,
                group=group,
                description=description,
                options=options,
                doc=self.doc,
            )
            if var:
                self.event_bus.var_created.emit(Variable(self.doc, name))
                self.event_bus.goto_home.emit()
            else:
                return str(dtr("Vars", "Variable '{name}' already exists.")).format(name=name)
        except Exception as e:  # noqa: BLE001
            return str(e)
        return None

    def do_edit_var(
        self,
        var: Variable,
        var_type: str,
        group: str,
        description: str,
        options: list[str] | None,
    ) -> str | None:
        if description != var.description:
            var.description = description

        if var_type != var.var_type and not var.change_var_type(var_type):
            return str(dtr("Vars", "Failed to set variable type."))

        if group and (group != var.group):
            var.group = group

        if options and (options != var.options):
            var.options = options

        self.event_bus.var_edited.emit(var)
        return None

    def on_var_edited(self, var: Variable) -> None:
        self.event_bus.var_deleted.emit(var)
        self.event_bus.var_created.emit(var)
        self.event_bus.goto_home.emit()

    def do_rename_var(self, var: Variable, new_name: str) -> None | str:
        try:
            if var.rename(new_name):
                self.event_bus.var_renamed.emit(var)
                self.event_bus.goto_home.emit()
                return None
            return str(dtr("Vars", "New variable name already exists."))
        except Exception as e:  # noqa: BLE001
            return str(e)

    def do_delete_var(self, var: Variable) -> None | str:
        try:
            if var.delete():
                self.event_bus.var_deleted.emit(var)
                self.event_bus.goto_home.emit()
                return None
            return str(dtr("Vars", "Failed to delete variable."))
        except Exception as e:  # noqa: BLE001
            return str(e)
