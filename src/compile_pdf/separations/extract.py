# SPDX-License-Identifier: AGPL-3.0-or-later
"""Walk an input PDF and enumerate every named separation per page.

Re-uses the Separation / DeviceN parsing pattern from
:mod:`compile_pdf_trap.extract` but is purpose-built for "list all
inks per page" — the trap version is scoped to "spot rectangles
adjacent to other spots", which is a different concern.

Process colors (DeviceCMYK, DeviceGray, CalRGB, ICCBased, …) are
NOT enumerated here — they are implicit on every page that contains
content. Only *named* separations (the things an operator would put
on a separate plate) are returned.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pikepdf
from pikepdf import Name, Object


@dataclass(frozen=True)
class SeparationInfo:
    """One named ink discovered in the input PDF.

    Aggregated by ``name`` across pages — a single ink that appears
    on three pages produces one ``SeparationInfo`` whose
    ``occurs_on_pages`` lists those three indices (0-indexed).
    """

    name: str
    color_space: str  # "Separation" | "DeviceN"
    occurs_on_pages: tuple[int, ...]


def list_separations(input_bytes: bytes) -> list[SeparationInfo]:
    """Return one entry per named separation, sorted by ink name.

    Walks every page's ``/Resources/ColorSpace`` dictionary. For each
    ``[/Separation, /InkName, …]`` entry, records ``InkName`` against
    the page index. For each ``[/DeviceN, [/Ink1, /Ink2, …], …]``
    entry, records each colorant in turn — DeviceN spaces can carry
    multiple inks on a single page.

    A given ink that appears as both Separation on page A and DeviceN
    on page B is reported once. The ``color_space`` field reflects
    the first occurrence seen during the walk — callers that need
    per-occurrence detail should re-walk with their own predicate.
    """
    by_name: dict[str, tuple[str, set[int]]] = {}

    pdf = pikepdf.open(io.BytesIO(input_bytes))
    try:
        for page_index, page in enumerate(pdf.pages):
            resources = page.obj.get(Name.Resources)
            if not isinstance(resources, pikepdf.Dictionary):
                continue
            cs_dict = resources.get(Name.ColorSpace)
            if not isinstance(cs_dict, pikepdf.Dictionary):
                continue
            for alias in list(cs_dict.keys()):
                space = cs_dict[alias]
                _record_space(space, page_index, by_name)
    finally:
        pdf.close()

    return [
        SeparationInfo(name=name, color_space=cs, occurs_on_pages=tuple(sorted(pages)))
        for name, (cs, pages) in sorted(by_name.items())
    ]


def _record_space(
    space: Object,
    page_index: int,
    by_name: dict[str, tuple[str, set[int]]],
) -> None:
    """Inspect one color-space array; record any Separation / DeviceN
    colorants against ``page_index`` in ``by_name``."""
    if not isinstance(space, pikepdf.Array) or len(space) < 2:
        return
    family = space[0]
    if family == Name.Separation:
        ink = _name_to_str(space[1])
        if ink:
            _record_ink(by_name, ink, "Separation", page_index)
    elif family == Name.DeviceN:
        names = space[1]
        if not isinstance(names, pikepdf.Array):
            return
        for n in names:
            ink = _name_to_str(n)
            if ink:
                _record_ink(by_name, ink, "DeviceN", page_index)


def _record_ink(
    by_name: dict[str, tuple[str, set[int]]],
    ink: str,
    color_space: str,
    page_index: int,
) -> None:
    if ink in by_name:
        existing_cs, pages = by_name[ink]
        pages.add(page_index)
        # Keep the first-seen color space; aggregation across spaces
        # is documented in the public docstring.
        by_name[ink] = (existing_cs, pages)
    else:
        by_name[ink] = (color_space, {page_index})


def _name_to_str(obj: Object) -> str | None:
    """Strip pikepdf's leading-slash on Name objects."""
    s = str(obj)
    if not s:
        return None
    return s.removeprefix("/") if s.startswith("/") else s
