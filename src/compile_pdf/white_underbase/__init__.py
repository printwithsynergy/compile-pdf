"""Wave 3 PR-7 — C2 white / underbase auto-generation producer.

Surfaces ``POST /v1/white-underbase/apply``. Given an input PDF
plus a policy describing how to derive a white-ink plate (or an
underbase plate for screen printing on dark fabric), the producer
adds a named DeviceN white separation to the output PDF.

Why this producer exists:

- White ink printing on transparent / dark substrates (labels,
  garment prints, foil-stamped artwork) needs a white plate that
  lays down under every printable element. Doing this by hand in
  Illustrator is error-prone; auto-generating from the existing
  ink coverage guarantees the white plate matches the colour
  artwork at every revision.
- Screen-printing on dark fabric needs an underbase plate (often
  white) so the coloured inks read true. Same registration
  problem, same auto-generation answer.
- Foil/metallic substrates use the same mechanism: a separation
  plate that activates wherever a "needs foil" tag exists in the
  artwork.

Engine status: today's engine is a passthrough that registers the
white separation entry in the output PDF's colour-space dictionary
but does not yet trace the underbase content (that lands in a
follow-up once the compose producer is live and the canonical
content tree is available to walk). The wire contract is final
so artwork-pdf hosts can wire UI today against a stable response
shape.

Module surface (mirrors trap / impose / marks / soft_proof):

- ``WHITE_UNDERBASE_SCHEMA_VERSION`` — bumped per spec §6.2 when
  the request / response shape changes.
- ``router`` — FastAPI router mounted under ``/v1/white-underbase``.
- ``apply_white_underbase`` — engine entry point.
"""

from __future__ import annotations

from compile_pdf.version import WHITE_UNDERBASE_SCHEMA_VERSION
from compile_pdf.white_underbase.api import router

__all__ = ["WHITE_UNDERBASE_SCHEMA_VERSION", "router"]
