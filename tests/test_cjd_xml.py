"""XML CJD encoding — round-trip + edge-case coverage."""

from __future__ import annotations

import base64

import pytest

from compile_pdf.cjd.schema import CjdJob
from compile_pdf.cjd.xml import CjdXmlError, parse_cjd_xml, render_cjd_xml


def _b64(data: bytes = b"%PDF-1.4\n%EOF") -> str:
    return base64.b64encode(data).decode("ascii")


def _round_trip(job: CjdJob) -> CjdJob:
    return parse_cjd_xml(render_cjd_xml(job))


def test_minimal_job_round_trips() -> None:
    original = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(),
            "steps": [{"type": "rewrite", "plan": {"ops": []}}],
        }
    )
    assert _round_trip(original) == original


def test_full_four_producer_chain_round_trips() -> None:
    original = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(),
            "job_id": "acme-12345",
            "strict_order": True,
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "X"}]},
                },
                {"type": "marks", "template": {"marks": [{"type": "proof_slug"}]}},
                {
                    "type": "impose",
                    "plan": {
                        "sheet": {"width_pt": 612, "height_pt": 792},
                        "cell": {"width_pt": 612, "height_pt": 792},
                    },
                },
                {
                    "type": "trap",
                    "policy": {
                        "trap_zones": [
                            {
                                "page_index": 0,
                                "rect_pt": [10, 10, 100, 100],
                                "from_ink": "Y",
                                "to_ink": "K",
                            }
                        ]
                    },
                },
            ],
        }
    )
    assert _round_trip(original) == original


def test_strict_order_attribute_round_trips() -> None:
    original = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(),
            "strict_order": False,
            "steps": [{"type": "rewrite", "plan": {"ops": []}}],
        }
    )
    restored = _round_trip(original)
    assert restored.strict_order is False


def test_unknown_root_element_rejected() -> None:
    with pytest.raises(CjdXmlError, match="expected root <cjd>"):
        parse_cjd_xml(b"<job><x/></job>")


def test_missing_input_rejected() -> None:
    with pytest.raises(CjdXmlError, match="<input_pdf_b64>"):
        parse_cjd_xml(
            b'<?xml version="1.0"?><cjd><steps><rewrite><plan>{"ops":[]}</plan></rewrite></steps></cjd>'
        )


def test_missing_steps_rejected() -> None:
    with pytest.raises(CjdXmlError, match="<steps>"):
        parse_cjd_xml(b'<?xml version="1.0"?><cjd><input_pdf_b64>x</input_pdf_b64></cjd>')


def test_unknown_step_type_rejected() -> None:
    body = (
        b'<?xml version="1.0"?>'
        b"<cjd>"
        b"<input_pdf_b64>x</input_pdf_b64>"
        b"<steps><lasso><plan>{}</plan></lasso></steps>"
        b"</cjd>"
    )
    with pytest.raises(CjdXmlError, match="unknown step type"):
        parse_cjd_xml(body)


def test_step_payload_missing_rejected() -> None:
    body = (
        b'<?xml version="1.0"?>'
        b"<cjd>"
        b"<input_pdf_b64>x</input_pdf_b64>"
        b"<steps><rewrite></rewrite></steps>"
        b"</cjd>"
    )
    with pytest.raises(CjdXmlError, match="missing or empty <plan>"):
        parse_cjd_xml(body)


def test_step_payload_invalid_json_rejected() -> None:
    body = (
        b'<?xml version="1.0"?>'
        b"<cjd>"
        b"<input_pdf_b64>x</input_pdf_b64>"
        b"<steps><rewrite><plan>not-json</plan></rewrite></steps>"
        b"</cjd>"
    )
    with pytest.raises(CjdXmlError, match="not valid JSON"):
        parse_cjd_xml(body)


def test_malformed_xml_rejected() -> None:
    with pytest.raises(CjdXmlError, match="malformed XML"):
        parse_cjd_xml(b"<cjd><unclosed>")


def test_xxe_billion_laughs_rejected() -> None:
    """defusedxml should reject entity expansion attacks."""
    body = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE lol [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        b"<cjd><input_pdf_b64>&lol2;</input_pdf_b64><steps/></cjd>"
    )
    with pytest.raises(CjdXmlError):
        parse_cjd_xml(body)
