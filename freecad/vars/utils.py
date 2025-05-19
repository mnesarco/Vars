# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Utils.
"""

from __future__ import annotations
import random
import binascii
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from FreeCAD import Document # type: ignore

_RAND = random.Random(time.time())  # noqa: S311 No cryptography

def get_unique_name(doc: Document, prefix: str = "XVar_") -> str:
    """
    Generate a unique name for an object in the given document.

    The generated name is a 8 character long hexadecimal string.
    The name is checked against the document's objects to ensure
    uniqueness. If the generated name is not unique the function
    will retry up to 10 times. If no unique name could be generated
    the function raises a RuntimeError.

    :param doc: The document in which the name should be unique.
    :return: A unique name
    """
    for _ in range(10):
        rand = binascii.hexlify(_RAND.randbytes(4)).decode("utf-8")
        name = f"{prefix}{rand}"
        if doc.getObject(name) is None:
            return name
    msg = "Could not generate unique name"
    raise RuntimeError(msg)


