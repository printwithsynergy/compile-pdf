"""XML CJD encoding — defusedxml-driven envelope.

The XML form is an envelope around the existing JSON payloads: each
producer step's ``plan`` / ``template`` / ``policy`` lives inside the
XML element as a CDATA-wrapped JSON string. Avoids re-mapping every
Pydantic model into XML attributes — operators integrating with
JDF / PJTF systems get an XML transport without a second schema to
maintain.

Round-trip property: ``parse_cjd_xml(render_cjd_xml(job)) == job``
for every valid CjdJob. Tests pin this against the discriminated
union plus all four producer plan shapes.

Security posture: parsing goes through ``defusedxml.ElementTree`` so
external entity / billion-laughs attacks are rejected.
"""

from __future__ import annotations

# Element and SubElement are write-only constructors; they never parse external
# input and carry no XXE risk. tostring is likewise output-only. All parsing
# goes through defusedxml.ElementTree below (see parse_cjd_xml).
from xml.etree.ElementTree import (  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml -- write-only constructors; no external-entity parsing path
    Element,
    SubElement,
)

import defusedxml.ElementTree as defused_etree  # noqa: N813
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import tostring  # output serialiser; safe (no parse)

from compile_pdf.cjd.schema import CjdJob

# Element names match the discriminator values in cjd/schema.py.
_STEP_TYPES = ("rewrite", "marks", "impose", "trap")
_STEP_PAYLOAD_KEY = {
    "rewrite": "plan",
    "marks": "template",
    "impose": "plan",
    "trap": "policy",
}


def render_cjd_xml(job: CjdJob) -> bytes:
    """Serialize a CjdJob to a UTF-8 XML byte-string."""
    import json

    root = Element("cjd")
    root.set("schema_version", job.schema_version)
    root.set("strict_order", "true" if job.strict_order else "false")
    if job.job_id is not None:
        root.set("job_id", job.job_id)

    input_el = SubElement(root, "input_pdf_b64")
    input_el.text = job.input_pdf_b64

    steps_el = SubElement(root, "steps")
    for step in job.steps:
        step_el = SubElement(steps_el, step.type)
        payload_key = _STEP_PAYLOAD_KEY[step.type]
        payload_el = SubElement(step_el, payload_key)
        # Each step has exactly one nested payload (plan/template/policy).
        payload = getattr(step, payload_key).model_dump(mode="json")
        payload_el.text = json.dumps(payload, separators=(",", ":"))

    rendered: bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return rendered


class CjdXmlError(ValueError):
    """The XML body is malformed or doesn't satisfy the CJD shape."""


def parse_cjd_xml(body: bytes | str) -> CjdJob:
    """Parse a CJD XML document into a :class:`CjdJob`.

    Raises :class:`CjdXmlError` for malformed XML, missing required
    elements, or unknown step types. Pydantic validation runs on the
    reconstructed dict so any payload-level error surfaces as a
    standard ``ValidationError`` from :class:`CjdJob.model_validate`.
    """
    import json

    try:
        root = defused_etree.fromstring(body)
    except defused_etree.ParseError as exc:
        raise CjdXmlError(f"malformed XML: {exc}") from exc
    except DefusedXmlException as exc:
        # XXE / billion-laughs / external-entity attacks
        raise CjdXmlError(f"unsafe XML rejected: {exc}") from exc
    if root.tag != "cjd":
        raise CjdXmlError(f"expected root <cjd>, got <{root.tag}>")

    input_el = root.find("input_pdf_b64")
    if input_el is None or not (input_el.text or "").strip():
        raise CjdXmlError("missing or empty <input_pdf_b64>")

    steps_root = root.find("steps")
    if steps_root is None:
        raise CjdXmlError("missing <steps>")

    steps: list[dict[str, object]] = []
    for step_el in list(steps_root):
        step_type = step_el.tag
        if step_type not in _STEP_TYPES:
            raise CjdXmlError(f"unknown step type <{step_type}>")
        payload_key = _STEP_PAYLOAD_KEY[step_type]
        payload_el = step_el.find(payload_key)
        if payload_el is None or not (payload_el.text or "").strip():
            raise CjdXmlError(f"step <{step_type}> missing or empty <{payload_key}> payload")
        try:
            payload = json.loads(payload_el.text)
        except json.JSONDecodeError as exc:
            raise CjdXmlError(
                f"step <{step_type}>/<{payload_key}> payload is not valid JSON: {exc}"
            ) from exc
        steps.append({"type": step_type, payload_key: payload})

    payload_dict: dict[str, object] = {
        "schema_version": root.get("schema_version", "1.0.0"),
        "input_pdf_b64": (input_el.text or "").strip(),
        "steps": steps,
        "strict_order": _bool_attr(root.get("strict_order")),
    }
    job_id = root.get("job_id")
    if job_id:
        payload_dict["job_id"] = job_id

    return CjdJob.model_validate(payload_dict)


def _bool_attr(value: str | None) -> bool:
    return (value or "").strip().lower() in ("true", "1", "yes")


__all__ = [
    "CjdXmlError",
    "parse_cjd_xml",
    "render_cjd_xml",
]
