"""HTTP surface for compile-pdf.

The four producer routers (rewrite, marks, impose, trap) mount onto the
shared FastAPI app at ``compile_pdf.api.main``. A producer service running
in standalone mode imports only the relevant router; the central all-in-one
deploy imports all four. Per spec §1.4: each producer service has its own
container, but the routers share the API skeleton (auth, middleware, lifecycle).
"""
