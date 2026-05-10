"""Marks engine — composes the rendered marks layer over an input PDF.

For each page in the input the engine:

1. Reads the page's MediaBox / TrimBox / BleedBox into a
   :class:`PageGeometry`.
2. Calls :func:`compile_pdf.marks.library.render` for every entry in
   the template, collecting the produced content-stream fragments.
3. Ensures the page's Resources dictionary has any required helpers
   (Helvetica ``/F1`` for text marks, Form XObjects for external PDF
   stamps, Image XObjects for external PNG stamps).
4. Appends the combined fragment as a new content stream on the page.

Determinism comes from ``Pdf.save(deterministic_id=True,
linearize=False)`` plus stable resource naming (``/MarkF1``,
``/MarkExt0``, …) seeded from the per-page rendering order. Re-running
the engine on the same input + template yields a byte-identical PDF.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Dictionary, Name, Object, Page, Pdf
from PIL import Image

from compile_pdf.marks.library import (
    PageGeometry,
    RenderedMark,
    render,
)
from compile_pdf.marks.template_schema import ExternalMark, MarksTemplate


@dataclass(frozen=True)
class MarksResult:
    """Outcome of stamping a template against an input PDF."""

    output_bytes: bytes
    pdf_sha256: str
    marks_applied: int


class MarksTemplateError(ValueError):
    """The template references something that cannot be resolved against
    the input (missing external file, invalid anchor, etc.). Raised
    before any mutation is committed to the output."""


def apply_template(
    input_bytes: bytes,
    template: MarksTemplate,
    *,
    external_root: Path | None = None,
) -> MarksResult:
    """Stamp ``template`` over ``input_bytes`` and return the rewritten PDF.

    ``external_root`` resolves relative paths in :class:`ExternalMark`
    entries. When ``None``, paths must be absolute or relative to the
    process CWD.
    """
    pdf = pikepdf.open(io.BytesIO(input_bytes))
    try:
        marks_applied = 0
        for page in pdf.pages:
            geom = _page_geometry(page)
            rendered: list[RenderedMark] = []
            for mark in template.marks:
                rendered.extend(render(mark, geom))
            if not rendered:
                continue
            _stamp_page(pdf, page, rendered, external_root=external_root)
            marks_applied += len(rendered)
        out = io.BytesIO()
        pdf.save(out, deterministic_id=True, linearize=False)
    finally:
        pdf.close()
    output_bytes = out.getvalue()
    return MarksResult(
        output_bytes=output_bytes,
        pdf_sha256=hashlib.sha256(output_bytes).hexdigest(),
        marks_applied=marks_applied,
    )


# --- Page-level helpers -------------------------------------------------


def _page_geometry(page: Page) -> PageGeometry:
    """Pull the page's box entries into a :class:`PageGeometry`."""
    media = _box_tuple(page.obj[Name.MediaBox])
    trim = _box_tuple(page.obj[Name.TrimBox]) if Name.TrimBox in page.obj else None
    bleed = _box_tuple(page.obj[Name.BleedBox]) if Name.BleedBox in page.obj else None
    return PageGeometry.from_boxes(media=media, trim=trim, bleed=bleed)


def _box_tuple(arr: Object) -> tuple[float, float, float, float]:
    return (float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3]))


def _stamp_page(
    pdf: Pdf,
    page: Page,
    rendered: list[RenderedMark],
    *,
    external_root: Path | None,
) -> None:
    """Combine all rendered fragments and append the result to ``page``."""
    resources = _ensure_resources(page)

    # Resolve externals first — they may inject content stream fragments
    # that reference resources we add below. ``ext_index`` is shared
    # across PDF + image externals so resource naming is stable.
    body_parts: list[bytes] = []
    needs_font = False
    ext_index = 0
    for r in rendered:
        if r.external_pdf is not None:
            body_parts.append(
                _embed_external_pdf(pdf, page, r.external_pdf, ext_index, external_root)
            )
            ext_index += 1
        elif r.external_image is not None:
            body_parts.append(
                _embed_external_image(pdf, page, r.external_image, ext_index, external_root)
            )
            ext_index += 1
        else:
            body_parts.append(r.stream)
            needs_font = needs_font or r.needs_font

    if needs_font:
        _ensure_helvetica(pdf, resources)

    overlay = b"q\n" + b"".join(body_parts) + b"Q\n"
    page.contents_add(pdf.make_stream(overlay), prepend=False)


def _ensure_resources(page: Page) -> Dictionary:
    if Name.Resources not in page.obj:
        page.obj[Name.Resources] = Dictionary()
    res = page.obj[Name.Resources]
    if not isinstance(res, Dictionary):  # pragma: no cover — malformed input
        raise MarksTemplateError("page has non-dict /Resources")
    return res


def _ensure_helvetica(pdf: Pdf, resources: Dictionary) -> None:
    """Add ``/Font << /F1 Helvetica >>`` to the page resources idempotently."""
    if Name.Font not in resources:
        resources[Name.Font] = Dictionary()
    fonts = resources[Name.Font]
    if Name("/F1") in fonts:
        return
    fonts[Name("/F1")] = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type1,
            BaseFont=Name("/Helvetica"),
            Encoding=Name.WinAnsiEncoding,
        )
    )


# --- External-file embedding --------------------------------------------


def _embed_external_pdf(
    pdf: Pdf,
    page: Page,
    mark: ExternalMark,
    index: int,
    external_root: Path | None,
) -> bytes:
    """Embed the first page of an external PDF as a Form XObject and
    place it at the chosen anchor.

    We bypass :meth:`Page.add_overlay` because pikepdf assigns the
    overlay XObject a randomized name (breaking determinism). Instead we
    convert the source page via :meth:`Page.as_form_xobject`, copy it
    into the target with :meth:`Pdf.copy_foreign`, and register it under
    a deterministic ``/MarkExtPdf{index}`` resource name.
    """
    src_path = _resolve_path(mark.file, external_root)
    try:
        src_pdf = pikepdf.open(src_path)
    except Exception as exc:
        raise MarksTemplateError(f"external PDF unreadable ({mark.file!r}): {exc}") from exc
    try:
        src_page = src_pdf.pages[0]
        form = src_page.as_form_xobject()
        bbox = form.get(Name.BBox)
        if bbox is None:
            raise MarksTemplateError(f"external PDF has no BBox: {mark.file!r}")
        src_w = float(bbox[2]) - float(bbox[0])
        src_h = float(bbox[3]) - float(bbox[1])
        copied = pdf.copy_foreign(form)
    finally:
        src_pdf.close()

    name = Name(f"/MarkExtPdf{index}")
    resources = _ensure_resources(page)
    if Name.XObject not in resources:
        resources[Name.XObject] = Dictionary()
    resources[Name.XObject][name] = copied

    ax, ay = _anchor_xy_for_page(page, mark)
    x0 = ax + mark.dx_pt
    y0 = ay + mark.dy_pt
    # BBox already encodes source extent in its own coords; cm uniformly
    # scales by ``mark.scale`` and translates to the anchor.
    _ = src_w, src_h  # surfaced for future asymmetric-scale support.
    return (
        f"q\n{mark.scale:.4f} 0 0 {mark.scale:.4f} {x0:.4f} {y0:.4f} cm\n{name} Do\nQ\n"
    ).encode("ascii")


def _embed_external_image(
    pdf: Pdf,
    page: Page,
    mark: ExternalMark,
    index: int,
    external_root: Path | None,
) -> bytes:
    """Embed a PNG as an Image XObject and place it at the chosen anchor."""
    src_path = _resolve_path(mark.file, external_root)
    try:
        img = Image.open(src_path).convert("RGB")
    except Exception as exc:
        raise MarksTemplateError(f"external PNG unreadable ({mark.file!r}): {exc}") from exc
    raw = img.tobytes()
    width, height = img.size
    img.close()

    name = Name(f"/MarkExt{index}")
    xobj = pdf.make_stream(
        raw,
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=width,
        Height=height,
        BitsPerComponent=8,
        ColorSpace=Name.DeviceRGB,
    )

    resources = _ensure_resources(page)
    if Name.XObject not in resources:
        resources[Name.XObject] = Dictionary()
    resources[Name.XObject][name] = xobj

    # Default placement: 1 pt per pixel, scaled by ``scale``.
    w_pt = width * mark.scale
    h_pt = height * mark.scale
    ax, ay = _anchor_xy_for_page(page, mark)
    x0 = ax + mark.dx_pt
    y0 = ay + mark.dy_pt
    return (f"q\n{w_pt:.4f} 0 0 {h_pt:.4f} {x0:.4f} {y0:.4f} cm\n{name} Do\nQ\n").encode("ascii")


def _anchor_xy_for_page(page: Page, mark: ExternalMark) -> tuple[float, float]:
    """Resolve a single-anchor coordinate for an external mark."""
    geom = _page_geometry(page)
    return geom.anchor_xy(mark.anchor)


def _resolve_path(file: str, external_root: Path | None) -> Path:
    candidate = Path(file)
    if candidate.is_absolute():
        if not candidate.exists():
            raise MarksTemplateError(f"external file not found: {file!r}")
        return candidate
    candidate = Path.cwd() / file if external_root is None else external_root / file
    if not candidate.exists():
        raise MarksTemplateError(f"external file not found: {file!r}")
    return candidate.resolve()


__all__ = [
    "MarksResult",
    "MarksTemplateError",
    "apply_template",
]
