# xpublish-ogc-core

OGC API - Common structure for xpublish: the landing page, conformance, and
collections endpoints, the hookspecs other OGC plugins (xpublish-edr,
xpublish-tiles) implement, and the shared compliance-testing helpers those
plugins import.

## Development

- Development is schema-driven: validate responses against the official OGC
  schemas vendored under `src/xpublish_ogc_core/schemas/` using
  `xpublish_ogc_core.testing.validate_response`. When a test fails against a
  schema, fix the implementation rather than loosening the test; genuinely
  out-of-scope gaps become documented known failures. Refresh the bundles
  with `python scripts/update_schemas.py` and commit them — tests must run
  offline.
- Run tests with `uv run pytest`. The CITE suites run from the downstream
  plugin repos via `xpublish_ogc_core.teamengine`; COMPLIANCE.md records
  what each test layer found and the TeamEngine quirks (default
  `ogctest:ogctest` credentials, no trailing slash on `iut`, the misleading
  missing-`apiDefinition` error).
- The uv_build backend packages everything under `src/xpublish_ogc_core/`,
  including `schemas/*.json`. When adding package data, verify it lands in
  the wheel with `uv build`.
- `build_collection()` merges `ogc_collection_metadata` and
  `ogc_collection_dataqueries` hook contributions and rewrites root-relative
  hrefs to absolute URLs — plugins may contribute relative hrefs, but
  clients (and the CITE suites) can't reliably resolve them.
