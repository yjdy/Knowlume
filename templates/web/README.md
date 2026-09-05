# Phase 4 Web resources

This directory is authoritative for the local read-only HTML templates, stylesheet, and vendored
HTMX runtime. Installed code loads the byte-identical wheel copy only through `importlib.resources`.

`assets/htmx.min.js` is HTMX 2.0.10 from the upstream release tag. See `vendor/HTMX-LICENSE.txt`
and `vendor/htmx-2.0.10.integrity.txt` for its license and SHA-256 record.
