# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

import xml.etree.ElementTree as ET  # nosec B405: parsing will be from defusedxml if available

try:
    from defusedxml import ElementTree as _DET
    safe_parse = _DET.parse
except ImportError:
    safe_parse = ET.parse

from .utils import BoolFlag


def update_elem_text(node: ET.Element, find: str, text: str, create: bool = False) -> BoolFlag:
    flag = BoolFlag()
    for child in node.iterfind(find):
        child.text = text
        flag()
    if not flag and create:
        add_element(node, find.split("/")[-1], text)
    return flag


def add_element(node: ET.Element, tag: str, text: str | None = None, **attrs) -> None:
    e = ET.Element(tag, {str(k): str(v) for k, v in attrs.items() if v is not None and v != ""})
    if text:
        e.text = text
    node.append(e)
