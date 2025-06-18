# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Editors UI.
"""

from __future__ import annotations

from functools import cache
import re
from contextlib import suppress
from typing import TYPE_CHECKING

from freecad.vars.vendor.fcapi.events import events
from freecad.vars.vendor.fcapi.lang import dtr, translate
from freecad.vars.vendor.fcapi import fcui as ui
from freecad.vars.api import (
    Variable,
    get_groups,
    create_var,
    export_variables,
    import_variables,
    VarGroup,
    VarContainer,
)
from freecad.vars.core.properties import (
    PROPERTY_INFO,
    PropertyAccessorAdapter,
    get_supported_property_types,
)
from itertools import chain
from freecad.vars.config import preferences, resources
from .style import FlatIcon, interpolate_style_vars, TEXT_COLOR
from textwrap import shorten, dedent
import contextlib
from . import widgets as uix

import FreeCAD as App  # type: ignore

if TYPE_CHECKING:
    from collections.abc import Generator, Callable
    from FreeCAD import Document, DocumentObject  # type: ignore
    from PySide6.QtWidgets import (
        QGraphicsOpacityEffect,
        QCompleter,
        QMenu,
        QAbstractSpinBox,
        QApplication,
        QSlider,
    )
    from PySide6.QtCore import QSettings, QObject, QEvent, QTimer

if not TYPE_CHECKING:
    from PySide.QtGui import (
        QGraphicsOpacityEffect,
        QCompleter,
        QMenu,
        QAbstractSpinBox,
        QApplication,
        QSlider,
    )
    from PySide.QtCore import QSettings, QObject, QEvent, QTimer

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


class VarEditor(QObject):
    """Variable editor row."""

    variable: Variable
    label: ui.InputTextWidget
    description: ui.QLabel
    editor: ui.InputQuantityWidget
    widget: ui.QWidget
    event_bus: EventBus
    lock_event_filter: LockEventFilter
    lock_action: ui.QAction
    scroll_event_filter: ScrollEventFilter
    row_layout: ui.QHBoxLayout

    def __init__(
        self,
        variable: Variable,
        event_bus: EventBus,
        add: bool = True,
        parent: QObject | None = None,
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
        self.lock_event_filter = LockEventFilter(self)
        self.lock_action = None
        self.scroll_event_filter = ScrollEventFilter(self)

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
                with ui.Row(contentsMargins=(0, 0, 0, 0), spacing=0) as row:
                    self.row_layout = row.layout()
                    self.label = ui.InputText(
                        var_display_label(variable.group, variable.name),
                        readOnly=True,
                        focusPolicy=ui.Qt.FocusPolicy.ClickFocus,
                        stretch=_UI_CACHE.get("LabelColumnStretch", 45),
                        styleSheet="font-weight: bold;",
                        toolTip=tooltip,
                        cursorPosition=0,
                    )
                    self.create_input_editor(tooltip)
                    self.create_menu_button()

            self.create_description(box)
            self.install_focus_style_listener()

        self.event_bus.column_width_change.connect(self.on_column_width_changed)

    def on_column_width_changed(self, value: int) -> None:
        self.row_layout.setStretchFactor(self.label, value)
        self.row_layout.setStretchFactor(self.editor, 100 - value)

    def install_focus_style_listener(self) -> None:
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
                stretch=100 - _UI_CACHE.get("LabelColumnStretch", 45),
            )
        else:
            self.editor = ui.InputQuantity(
                obj=variable.varset,
                property="Value",
                auto_apply=True,
                stretch=100 - _UI_CACHE.get("LabelColumnStretch", 45),
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

        self.lock_ui(variable.read_only)
        self.update_visibility_ui()
        self.scroll_event_filter.install(self.editor)

        return self.editor

    def lock_ui(self, lock: bool = True) -> None:
        if lock:
            self.lock_event_filter.install(self.editor)
            icon = FlatIcon(resources.icon("locked.svg"))
            setattr(  # noqa: B010
                self.label,
                "_lock_icon",
                self.label.addAction(icon, ui.QLineEdit.ActionPosition.TrailingPosition),
            )
        else:
            self.lock_event_filter.uninstall(self.editor)
            if action := getattr(self.label, "_lock_icon", None):
                self.label.removeAction(action)
            setattr(self.label, "_lock_icon", None)  # noqa: B010

    def update_visibility_ui(self) -> None:
        hidden = self.variable.hidden
        if hidden:
            icon = FlatIcon(resources.icon("hidden_ind.svg"))
            setattr(  # noqa: B010
                self.label,
                "_hidden_icon",
                self.label.addAction(icon, ui.QLineEdit.ActionPosition.TrailingPosition),
            )
        else:
            if action := getattr(self.label, "_hidden_icon", None):
                self.label.removeAction(action)
            setattr(self.label, "_hidden_icon", None)  # noqa: B010

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
        if var == self.variable:
            self.label.setText(var_display_label(var.group, var.name))
            self.label.setToolTip(self.var_tooltip())
            self.description.setText(var.description)
            self.update_visibility_ui()
            self.silent_value_update(var)

    def silent_value_update(self, var: Variable) -> None:
        if var != self.variable:
            self.editor.blockSignals(True)
            self.editor.setValue(self.variable.value)
            self.editor.blockSignals(False)

    def var_tooltip(self) -> str:
        var = self.variable
        return dedent(f"""
            <p>{var.name}: {shorten(var.description, 255, placeholder="...")}</p>
            <pre>Type: {var.var_type}
            Reference: &lt;&lt;{var.name}&gt;&gt;.Value
            Python: freecad.vars.api.get_var("{var.name}", doc)</pre>
            """)

    def create_menu_button(self) -> None:
        ui.Button(
            text="...",
            tool=True,
            popupMode=ui.QToolButton.ToolButtonPopupMode.InstantPopup,
            arrowType=ui.Qt.ArrowType.NoArrow,
            toolButtonStyle=ui.Qt.ToolButtonStyle.ToolButtonTextOnly,
            styleSheet="QToolButton::menu-indicator { image: none; }",
            focusPolicy=ui.Qt.FocusPolicy.NoFocus,
            clicked=self.popup_menu,
        )

    def popup_menu(self) -> None:
        menu = QMenu()

        add_action(
            menu,
            text=translate("Vars", "Rename"),
            receiver=self.cmd_rename,
            icon="rename.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Show references"),
            receiver=self.cmd_references,
            icon="reference.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Change definition"),
            receiver=self.cmd_edit,
            icon="edit.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Delete"),
            receiver=self.cmd_delete,
            icon="delete.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Unlock")
            if self.variable.read_only
            else translate("Vars", "Lock"),
            receiver=self.cmd_lock,
            icon="unlock.svg" if self.variable.read_only else "lock.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Restore visibility")
            if self.variable.hidden
            else translate("Vars", "Hide"),
            receiver=self.cmd_hide,
            icon="visible.svg" if self.variable.hidden else "hidden.svg",
        )

        menu.addSeparator()

        add_action(
            menu,
            text=translate("Vars", "Move to top"),
            receiver=self.cmd_sort_top,
            icon="sort-top.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Move up"),
            receiver=self.cmd_sort_up,
            icon="sort-up.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Move down"),
            receiver=self.cmd_sort_down,
            icon="sort-down.svg",
        )

        add_action(
            menu,
            text=translate("Vars", "Move to bottom"),
            receiver=self.cmd_sort_bottom,
            icon="sort-bottom.svg",
        )

        btn: ui.QToolButton = self.sender()
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def cmd_sort_top(self) -> None:
        self.variable.reorder(float("-inf"))
        self.event_bus.var_reordered.emit(self)

    def cmd_sort_bottom(self) -> None:
        self.variable.reorder(float("inf"))
        self.event_bus.var_reordered.emit(self)

    def cmd_sort_up(self) -> None:
        self.variable.reorder(-1)
        self.event_bus.var_reordered.emit(self)

    def cmd_sort_down(self) -> None:
        self.variable.reorder(1)
        self.event_bus.var_reordered.emit(self)

    def filter(self, text: str, show_hidden: bool = False) -> None:
        if not text or text.lower() in self.variable.name.lower():
            set_visibility(self.widget, (not self.variable.hidden) or show_hidden)
            return
        set_visibility(self.widget, False)

    def cmd_lock(self) -> None:
        read_only = not self.variable.read_only
        self.variable.read_only = read_only
        self.lock_ui(read_only)

    def cmd_hide(self) -> None:
        hidden = not self.variable.hidden
        self.variable.hidden = hidden
        self.update_visibility_ui()
        self.event_bus.filter_changed.emit()

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

    def __lt__(self, other: VarEditor) -> bool:
        return self.variable < other.variable


class EventBus(QObject):
    """Event bus for async inter-object communication."""

    goto_home = ui.Signal()
    goto_create_var = ui.Signal()
    goto_edit_var = ui.Signal(Variable)
    goto_rename_var = ui.Signal(Variable)
    goto_delete_var = ui.Signal(Variable)
    goto_var_references = ui.Signal(Variable)
    goto_groups = ui.Signal()

    variable_changed = ui.Signal(Variable)

    var_renamed = ui.Signal(Variable)
    var_delete_requested = ui.Signal(Variable)
    var_editor_removed = ui.Signal(Variable)
    var_created = ui.Signal(Variable)
    var_edited = ui.Signal(Variable)
    var_group_will_change = ui.Signal(Variable)
    var_reordered = ui.Signal(object)

    request_focus = ui.Signal(str)

    remove_var_editor = ui.Signal(VarEditor)
    filter_changed = ui.Signal()

    reload_vars = ui.Signal()

    column_width_change = ui.Signal(int)

    def __init__(self, *args) -> None:  # noqa: D107
        super().__init__(*args)


class VarGroupSection(QObject):
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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.event_bus = event_bus

        with ui.GroupBox(
            title=name,
            contentsMargins=(2, 2, 2, 2),
            objectName=f"VarsGroupBox{hash(name)}",
            styleSheet=f"QGroupBox[objectName='VarsGroupBox{hash(name)}'] {{margin-bottom: 20;}}",
            add=add,
        ) as box:
            self.container = box
            box.groupInstance = self
            with ui.Col(contentsMargins=(2, 2, 2, 2), spacing=0) as col:
                self.editors_layout = col.layout()
                self.editors = [
                    VarEditor(var, event_bus, parent=self) for var in variables if var.group == name
                ]

        event_bus.var_delete_requested.connect(self.on_delete_requested)
        event_bus.var_reordered.connect(self.on_var_reordered)
        event_bus.var_group_will_change.connect(self.remove_var_editor)

    def on_var_reordered(self, editor: VarEditor | None) -> None:
        if editor is None or editor in self.editors:
            self.editors.sort()
            layout = self.editors_layout
            for ed in self.editors:
                layout.removeWidget(ed.widget)
                layout.addWidget(ed.widget)
            layout.activate()

    def on_delete_requested(self, var: Variable) -> None:
        self.remove_var_editor(var)
        self.event_bus.var_editor_removed.emit(var)

    def remove_var_editor(self, var: Variable) -> None:
        editors = [e for e in self.editors if e.variable == var]
        if editors:
            editor = editors[0]
            self.editors_layout.removeWidget(editor.widget)
            self.editors.remove(editor)
            editor.widget.deleteLater()
            editor.deleteLater()

    def filter(self, text: str, show_hidden: bool = False) -> None:
        visible = False
        for editor in self.editors:
            editor.filter(text, show_hidden)
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
            self.on_var_reordered(editor)
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


class UIPage(QObject):
    """View: Base class for pages."""

    editor: VariablesEditor
    page_id: int
    event_bus: EventBus
    dialog: ui.QWidget
    doc: Document

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
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
    search: ui.InputTextWidget
    show_hidden: bool
    column_slider: QSlider

    def __init__(
        self,
        editor: VariablesEditor,
        groups: list[tuple[str, list[Variable]]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(editor, parent)
        self.auto_recompute = False
        self.show_hidden = preferences.Hidden.show_hidden_vars()
        with ui.Col():
            self.create_toolbar()
            editor.search = self.create_search_box()
            self.create_column_slider()
            with (
                ui.Scroll(widgetResizable=True) as scroll,
                ui.Container(),
                ui.Col(
                    contentsMargins=(0, 0, 0, 0),
                    spacing=0,
                    alignment=ui.Qt.AlignmentFlag.AlignTop,
                ),
            ):
                bus = self.event_bus
                self.create_sections(groups)
                ui.Stretch(1)

                self.scroll = scroll
                bus.request_focus.connect(self.on_request_focus)

        self.event_bus.variable_changed.connect(self.recompute)
        self.event_bus.reload_vars.connect(self.reload_content)

    def create_column_slider(self) -> None:
        with ui.Row(contentsMargins=(10, 0, 40, 0)):
            slider = QSlider()
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(_UI_CACHE.get("LabelColumnStretch", 45))
            slider.setOrientation(ui.Qt.Orientation.Horizontal)
            slider.setTickPosition(QSlider.TickPosition.NoTicks)
            slider.setFocusPolicy(ui.Qt.FocusPolicy.NoFocus)
            ui.place_widget(slider)
            slider.valueChanged.connect(self.on_column_width_change)
            self.column_slider = slider

    def on_column_width_change(self, value: int) -> None:
        MIN, MAX = 20, 70
        if value < MIN:
            value = MIN
            self.column_slider.setValue(value)
        elif value > MAX:
            value = MAX
            self.column_slider.setValue(value)
        _UI_CACHE["LabelColumnStretch"] = value
        self.event_bus.column_width_change.emit(value)

    def recompute(self, var: Variable) -> None:
        if self.auto_recompute:
            var.document.recompute()

    def create_sections(self, groups: list[tuple[str, list[Variable]]], add: bool = True) -> None:
        with ui.Col(spacing=0, add=add) as col:
            col.layout().setAlignment(ui.Qt.AlignmentFlag.AlignTop)
            col.setObjectName("_VarsEditorHomeContent_")
            bus = self.event_bus
            self.editor.sections_layout = col.layout()
            self.editor.sections = [
                VarGroupSection(name, items, bus, parent=self) for name, items in groups
            ]
        return col

    def reload_content(self) -> None:
        from freecad.vars.commands import EditVars

        App.Gui.runCommand(EditVars.name)

    def on_request_focus(self, name: str) -> None:
        def task() -> None:
            if widget := self.dialog.findChild(ui.QWidget, name):
                if self.scroll.isAncestorOf(widget):
                    self.scroll.ensureWidgetVisible(widget.parent())
                widget.setFocus()

        ui.QTimer.singleShot(100, task)

    def create_search_box(self) -> ui.QWidget:
        with ui.Row(contentsMargins=(0, 0, 0, 0)):
            self.search = ui.InputText(placeholderText=str(dtr("Vars", "Search...")), stretch=1)
            self.search.textChanged.connect(self.editor.cmd_filter)
            return self.search

    def create_toolbar(self) -> ui.QWidget:
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
            toolbar_button(
                icon="groups.svg",
                tooltip=str(dtr("Vars", "Manage groups")),
                callback=editor.cmd_manage_groups,
            )
            self.toggle_hidden_btn()
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

    def toggle_hidden_btn(self) -> None:
        visible_icon = resources.icon("visible.svg")
        hidden_icon = resources.icon("hidden.svg")
        visible_tooltip = translate("Vars", "Hidden vars are visible, click to hide.")
        hidden_tooltip = translate("Vars", "Show hidden vars")
        self.show_hidden = preferences.Hidden.show_hidden_vars()

        def toggle() -> None:
            self.show_hidden = not self.show_hidden
            preferences.Hidden.show_hidden_vars(update=self.show_hidden)
            if self.show_hidden:
                btn.setIcon(FlatIcon(visible_icon))
                btn.setToolTip(visible_tooltip)
            else:
                btn.setIcon(FlatIcon(hidden_icon))
                btn.setToolTip(hidden_tooltip)
            self.editor.cmd_filter()

        btn = toolbar_button(
            icon=visible_icon if self.show_hidden else hidden_icon,
            tooltip=str(visible_tooltip) if self.show_hidden else str(hidden_tooltip),
            callback=toggle,
        )

    def toggle_auto_recompute(
        self,
        pause_icon: str,
        pause_tooltip: dtr,
        auto_icon: str,
        auto_tooltip: dtr,
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

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
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

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
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
                    self.name = ui.InputText(value="", maxLength=128)

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
                    self.groups.lineEdit().setMaxLength(128)

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
                            max_length=4096,
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
                translate("Vars", "Invalid property type selected."),
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


class GroupItem(ui.QFrame):
    """
    Group editor row.
    """

    order_changed = ui.Signal()
    name_changed = ui.Signal()

    group: VarGroup
    rename_input: ui.QLineEdit

    def __init__(self, group: VarGroup, parent: ui.QWidget | None = None) -> None:
        super().__init__(parent)
        self.group = group

        self.rename_input = ui.QLineEdit(self)
        self.rename_input.setText(self.group.name)

        self.menu = ui.QToolButton(self)
        self.menu.setText("...")
        self.menu.setPopupMode(ui.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu.setArrowType(ui.Qt.ArrowType.NoArrow)
        self.menu.setToolButtonStyle(ui.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.menu.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.menu.setFocusPolicy(ui.Qt.FocusPolicy.NoFocus)

        hidden_btn = ui.QToolButton(self)
        hidden_btn.setIcon(
            FlatIcon(
                resources.icon("hidden_ind.svg" if group.hidden else "visible.svg"),
            ),
        )
        hidden_btn.setToolButtonStyle(ui.Qt.ToolButtonStyle.ToolButtonIconOnly)
        hidden_btn.setToolTip(translate("Vars", "Toggle visibility"))
        hidden_btn.setFocusPolicy(ui.Qt.FocusPolicy.NoFocus)
        hidden_btn.clicked.connect(self.on_toggle_visibility)

        add_action(
            self.menu,
            text=translate("Vars", "Move to top"),
            icon="sort-top.svg",
            receiver=lambda: self.reordered(float("-inf")),
        )

        add_action(
            self.menu,
            text=translate("Vars", "Move up"),
            icon="sort-up.svg",
            receiver=lambda: self.reordered(-1.5),
        )

        add_action(
            self.menu,
            text=translate("Vars", "Move down"),
            icon="sort-down.svg",
            receiver=lambda: self.reordered(1.5),
        )

        add_action(
            self.menu,
            text=translate("Vars", "Move to bottom"),
            icon="sort-bottom.svg",
            receiver=lambda: self.reordered(float("inf")),
        )

        layout = ui.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.rename_input, 1)
        layout.addWidget(hidden_btn)
        layout.addWidget(self.menu)
        self.setLayout(layout)

    def on_toggle_visibility(self) -> None:
        group = self.group
        group.hidden = not group.hidden
        self.sender().setIcon(
            FlatIcon(
                resources.icon("hidden_ind.svg" if group.hidden else "visible.svg"),
            ),
        )

    def reordered(self, delta: float) -> None:
        self.group.sort_key = self.group.sort_key + delta
        self.order_changed.emit()

    def __lt__(self, other: GroupItem) -> bool:
        return self.group < other.group

    def apply_changes(self) -> None:
        new_name = self.rename_input.text().strip().title()
        if new_name != self.group.name:
            self.group.rename(new_name)
            self.name_changed.emit()


class GroupManagementPage(UIPage):
    """View: Reorder/Rename groups."""

    container: VarContainer
    editors_layout: ui.QVBoxLayout
    editors: list[GroupItem]
    root: ui.QWidget

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(editor, parent)
        self.container = VarContainer()

        with ui.Col():
            with ToolBar():
                toolbar_button(
                    icon="arrow-back.svg",
                    tooltip=str(dtr("Vars", "Cancel")),
                    callback=self.on_cancel,
                )
                toolbar_button(
                    icon="check-mark.svg",
                    tooltip=str(dtr("Vars", "Apply changes")),
                    callback=self.on_apply,
                )

            with ui.GroupBox(title=str(dtr("Vars", "Manage groups"))) as root:
                self.root = root
                with (
                    ui.Scroll(widgetResizable=True),
                    ui.Container(),
                    ui.Col(contentsMargins=(0, 0, 0, 0), spacing=0),
                ):
                    with ui.Col(contentsMargins=(0, 0, 0, 0), spacing=0) as col:
                        self.editors_layout = col.layout()
                    self.editors = []
                    ui.Stretch(1)

    def load_groups(self) -> None:
        layout = self.editors_layout
        for ed in self.editors:
            ed.deleteLater()
        editors = self.editors = []
        root = self.root
        for i in range(layout.count()):
            layout.takeAt(i)

        for g in self.container.groups():
            row = GroupItem(g, root)
            row.order_changed.connect(self.on_reordered)
            editors.append(row)
            layout.addWidget(row)

    def on_cancel(self) -> None:
        self.event_bus.goto_home.emit()

    def on_apply(self) -> None:
        names = []
        hidden = []
        for ge in self.editors:
            ge.apply_changes()
            names.append(ge.group.name)
            if ge.group.hidden:
                hidden.append(ge.group.name)
        self.container.reorder(names)
        self.container.set_hidden(hidden)
        self.event_bus.reload_vars.emit()

    def on_reordered(self) -> None:
        self.editors.sort()
        for index, ge in enumerate(self.editors):
            ge.group.sort_key = index

        layout = self.editors_layout
        for ge in self.editors:
            layout.removeWidget(ge)
            layout.addWidget(ge)


class VarRenamePage(UIPage):
    """View: Rename variable form page."""

    old: ui.InputTextWidget
    new: ui.InputTextWidget
    var: Variable
    message: ui.QLabel
    references: ReferencesTable

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
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

    def __init__(
        self,
        editor: VariablesEditor,
        parent: QObject | None = None,
    ) -> None:
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
                                "Deleting variables will break all references to it.",
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

                        self.confirm.toggled.connect(self.button.setEnabled)

                    self.references = ReferencesTable(
                        str(dtr("Vars", "Known References (Will break)")),
                    )

                    ui.Stretch(1)
                    self.message = ui.TextLabel("", wordWrap=True)

    def on_cancel(self) -> None:
        self.event_bus.goto_home.emit()

    def on_delete(self) -> None:
        self.event_bus.var_delete_requested.emit(self.var)

    def set_var(self, var: Variable) -> None:
        self.var = var
        self.confirm.setChecked(False)
        self.button.setText(str(dtr("Vars", "Delete {name}")).format(name=var.name))
        self.message.setText("")
        self.name.setText(var.name)
        self.references.update(var)


class VariablesEditor(QObject):
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
    groups_page: GroupManagementPage

    q_settings = QSettings("FreeCAD", "mnesarco-Vars")

    QObjectName = "Vars_EditorInstance"

    def __init__(self, doc: Document) -> None:
        super().__init__(App.Gui.getMainWindow())
        self.setObjectName(self.QObjectName)
        self.doc = doc
        groups = self.get_groups()
        x, y, w, h = self.get_geometry()

        with ui.Dialog(
            title=str(dtr("Vars", "Variables")),
            styleSheet=stylesheet,
            modal=False,
            parent=App.Gui.getMainWindow(),
            size=(w, h),
        ) as dialog:
            dialog.setAttribute(ui.Qt.WidgetAttribute.WA_DeleteOnClose, False)
            self.dialog = dialog
            self.event_bus = EventBus(self)
            with ui.Stack() as pages:
                self.pages = pages.layout()
                self.home_page = HomePage(self, groups, dialog)
                self.edit_page = VarEditPage(self, dialog)
                self.rename_page = VarRenamePage(self, dialog)
                self.references_page = VarReferencesPage(self, dialog)
                self.delete_page = VarDeletePage(self, dialog)
                self.groups_page = GroupManagementPage(self, dialog)

        if x or y:
            dialog.setGeometry(x, y, w, h)
        QTimer.singleShot(0, self.ensure_valid_geometry)

        self.init_events()
        self.cmd_filter()

        dialog.onMove.connect(self.on_move_or_resize)
        dialog.onResize.connect(self.on_move_or_resize)
        dialog.onClose.connect(self.on_dialog_destroyed)
        dialog.destroyed.connect(self.on_dialog_destroyed)
        self.destroyed.connect(self.on_destroyed)

        def on_document_activated(event: events.DocumentEvent) -> None:
            from freecad.vars.commands import EditVars

            if event.doc != self.doc:
                QTimer.singleShot(0, lambda: App.Gui.runCommand(EditVars.name))

        self.on_document_activated = events.document.activated(on_document_activated)

    def unsubscribe(self) -> None:
        if self.on_document_activated:
            with suppress(RuntimeWarning):
                self.on_document_activated.unsubscribe()
            self.on_document_activated = None

    def on_dialog_destroyed(self) -> None:
        self.unsubscribe()
        self.dialog = None

    def close(self) -> None:
        self.on_destroyed()
        self.deleteLater()

    def on_destroyed(self) -> None:
        self.unsubscribe()
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()

    def ensure_valid_geometry(self) -> None:
        dialog_geom = self.dialog.frameGeometry()
        for screen in (s.availableGeometry() for s in QApplication.screens()):
            if screen.intersects(dialog_geom):
                return
        screen_center = QApplication.primaryScreen().availableGeometry().center()
        self.dialog.move(screen_center - dialog_geom.center())

    def get_geometry(self) -> tuple[int, int, int, int]:
        x = self.q_settings.value("x", 0, int)
        y = self.q_settings.value("y", 0, int)
        w = self.q_settings.value("w", 0, int)
        h = self.q_settings.value("h", 0, int)
        return max(x, 0), max(y, 0), max(w, 400), max(h, 500)

    def on_move_or_resize(self, _e) -> None:
        geom = self.dialog.geometry()
        self.q_settings.setValue("x", geom.left())
        self.q_settings.setValue("y", geom.top())
        self.q_settings.setValue("w", geom.width())
        self.q_settings.setValue("h", geom.height())

    def get_groups(self) -> list[(str, list[Variable])]:
        supported_types = get_supported_property_types()
        visible_groups = [g for g in VarContainer(self.doc).groups() if not g.hidden]
        return [
            (g.name, [v for v in g.variables() if v.var_type in supported_types])
            for g in visible_groups
        ]

    def init_events(self) -> None:
        bus = self.event_bus
        bus.goto_edit_var.connect(self.cmd_edit_var)
        bus.goto_rename_var.connect(self.cmd_rename_var)
        bus.goto_home.connect(self.on_home)
        bus.goto_var_references.connect(self.cmd_var_references)
        bus.goto_delete_var.connect(self.cmd_delete_var)
        bus.goto_groups.connect(self.cmd_manage_groups)
        bus.var_created.connect(self.on_var_created)
        bus.var_edited.connect(self.on_var_edited)
        bus.var_editor_removed.connect(self.do_delete_var)
        bus.filter_changed.connect(self.cmd_filter)

    def cmd_manage_groups(self) -> None:
        self.groups_page.load_groups()
        self.switch_to_page(self.groups_page)

    def do_delete_var(self, var: Variable) -> None:
        var.delete()
        ui.QTimer.singleShot(10, lambda: self.event_bus.goto_home.emit())

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
                var.group,
                [var],
                self.event_bus,
                add=False,
                parent=self.dialog,
            )
            self.sections.append(new_section)
            self.sections_layout.addWidget(new_section.container)
            ui.build_context().reset()
            ui.QApplication.instance().processEvents()
            self.sections_layout.activate()
            self.event_bus.request_focus.emit(new_section.editors[0].editor.objectName())

    def on_home(self) -> None:
        self.switch_to_page(self.home_page)
        self.cmd_filter()

    def cmd_rename_var(self, var: Variable) -> None:
        self.rename_page.set_var(var)
        self.switch_to_page(self.rename_page)

    def cmd_filter(self, text: str | None = None) -> None:
        for section in self.sections:
            section.filter(text or self.search.text(), self.home_page.show_hidden)

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
        self.event_bus.var_group_will_change.emit(var)
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


@cache
def var_display_label(group: str, name: str) -> str:
    """Get the display label for a variable."""
    try:
        parts = [p for p in _DISPLAY_LABEL_SEP.split(name) if p]
        if len(parts) > 1 and group.lower() == parts[0].lower():
            parts.pop(0)
        return " ".join(p.capitalize() for p in parts)
    except Exception:  # noqa: BLE001
        return name


class ScrollEventFilter(QObject):
    """
    Prevents accidental changes on scroll.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            return not (isinstance(obj, ui.QWidget) and obj.hasFocus())
        return super().eventFilter(obj, event)

    def install(self, target: ui.QWidget) -> None:
        for child in chain(target.findChildren(ui.QWidget), [target]):
            if isinstance(child, QAbstractSpinBox):
                child.installEventFilter(self)
                child.setFocusPolicy(ui.Qt.FocusPolicy.StrongFocus)


class LockEventFilter(QObject):
    """
    Lock input without disabling the widget.
    """

    interactive_events = frozenset((
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.KeyPress,
        QEvent.Type.KeyRelease,
        QEvent.Type.Wheel,
        QEvent.Type.FocusIn,
        QEvent.Type.FocusOut,
        QEvent.Type.Enter,
        QEvent.Type.Leave,
        # QEvent.Type.HoverEnter,
        # QEvent.Type.HoverLeave,
        # QEvent.Type.HoverMove,
        QEvent.Type.ContextMenu,
        QEvent.Type.TouchBegin,
        QEvent.Type.TouchUpdate,
        QEvent.Type.TouchEnd,
    ))

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in LockEventFilter.interactive_events:
            return True
        return super().eventFilter(obj, event)

    def install(self, target: ui.QWidget) -> None:
        target.installEventFilter(self)
        for child in target.findChildren(ui.QWidget):
            child.installEventFilter(self)

    def uninstall(self, target: ui.QWidget) -> None:
        target.removeEventFilter(self)
        for child in target.findChildren(ui.QWidget):
            child.removeEventFilter(self)


_DISPLAY_LABEL_SEP = re.compile(r"_|(?=[A-Z])")

_UI_CACHE = {
    "LabelColumnStretch": 45,
}
