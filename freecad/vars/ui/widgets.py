# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from freecad.vars.vendor.fcapi import fcui as ui
from FreeCAD import DocumentObject


class PropertyEnumerationWidget(ui.QComboBox):
    """
    Property Enumeration Widget.
    """

    valueChanged = ui.Signal(object)
    obj: DocumentObject
    prop_name: str
    accessor_adapter: ui.PropertyAccessorAdapter

    def __init__(
        self,
        obj: DocumentObject,
        prop_name: str,
        accessor_adapter: ui.PropertyAccessorAdapter,
        stretch: int = 0,
        objectName: str | None = None,
    ) -> None:
        super().__init__()
        self.obj = obj
        self.prop_name = prop_name
        self.accessor_adapter = accessor_adapter
        self.setEditable(False)

        if objectName:
            self.setObjectName(objectName)

        self.currentIndexChanged.connect(self.on_index_changed)

        for item in obj.getEnumerationsOfProperty(prop_name):
            self.addItem(item, item)

        self.setCurrentIndex(self.findData(accessor_adapter.get(obj, prop_name)))

        ui.place_widget(self, stretch=stretch)

    def on_index_changed(self, index: int) -> None:
        text = self.itemData(index) or ""
        self.accessor_adapter.set(self.obj, self.prop_name, text)
        self.valueChanged.emit(text)

    def value(self) -> str:
        return self.itemData(self.currentIndex()) or ""

    text = value

    def setValue(self, value: str) -> None:
        self.setCurrentIndex(self.findData(value))
