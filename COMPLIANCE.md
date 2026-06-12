# Compliance testing

xpublish-ogc-core is developed against the official OGC artifacts instead of
hand-approximated responses, through three layers of testing:

1. **Schema validation** — every endpoint's body is validated against the
   official OGC schemas vendored under `src/xpublish_ogc_core/schemas/`
   (refresh with `uv run scripts/update_schemas.py`). Core's own responses
   validate against the **OGC API - Common** building blocks (the `"common"`
   document: Common Part 1 plus the collections shapes from Features Part 1,
   which the unpublished Common Part 2 derives from); the standard-specific
   bundles (`"edr"`, `"tiles"`) are vendored for the plugin repos that
   implement those standards. The helpers in `xpublish_ogc_core.testing`
   are shipped with the package so downstream plugins can do the same.
1. **Schemathesis fuzzing** — `tests/test_schemathesis.py` generates requests
   from the app's own OpenAPI description and validates the responses
   against it.
1. **OGC CITE executable test suites** — `xpublish_ogc_core.teamengine` runs
   the official `ogccite/ets-*` Docker images via TeamEngine's REST API.
   There is no executable test suite for OGC API - Common itself, so
   `tests/test_cite.py` runs the EDR suite against the core plugin composed
   with a stub OGC plugin: its Common subset (landing page, api definition,
   conformance declaration, collections structure) directly exercises core's
   endpoints, with the EDR-specific expectations in a known-failures list
   (the suite demands the EDR conformance class, which a Common-only server
   correctly does not declare). The full standard-specific suites run in the
   plugin repos (`tests/test_teamengine.py` in xpublish-edr and
   xpublish-tiles), whose landing page, conformance, and collections
   responses are also served by this plugin.

## What the tests found

Each of these was caught by a test layer and fixed in this repo:

| Found by                                                                                          | Error                                                                                                                                                                                                        | Change                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `validate_response("collections", ...)` against the official `collections` schema                 | `/collections` returned a bare list of dataset ids                                                                                                                                                           | Spec-shaped `Collections` body with `links` and full collection objects built by a shared `build_collection()` helper                                                                                                 |
| `validate_response("collection", ...)`                                                            | Collection objects were missing the keys the `collection` schema requires (`links`, `extent`, `crs`, `output_formats`, `parameter_names`)                                                                    | Base keys with empty defaults, merged with plugin contributions from the `ogc_collection_metadata` / `ogc_collection_dataqueries` hooks                                                                               |
| `validate_response("exception", ...)`                                                             | Unknown collection ids returned FastAPI's `{"detail": ...}` body                                                                                                                                             | OGC `exception`-shaped 404 bodies (`{"code", "description"}`)                                                                                                                                                         |
| CITE ets-ogcapi-edr10, `CollectionsResponse.verifyCollectionsMetadata` (EDR 1.0 Abstract Test 15) | Collections in `/collections` had no `data` or `collection` rel link                                                                                                                                         | Each collection links to itself with `rel: collection` in addition to `rel: self`                                                                                                                                     |
| CITE ets-ogcapi-tiles10, `GeospatialDataResource.*` and `Tile.*`                                  | Root-relative link hrefs contributed by plugins are resolved by the CITE suites as `scheme://host` + href, dropping the port                                                                                 | `build_collection()` rewrites relative hrefs in contributed links and `data_queries` to absolute URLs                                                                                                                 |
| `validate_response("collection", ..., document="common")`                                         | Core injected EDR-specific members (`extent: {}`, `crs: []`, `output_formats: []`, `parameter_names: {}`, and an unconditional `data_queries`) into every collection, even on servers without the EDR plugin | Core's base collection is a minimal Common collection (`id`, `links`, attrs-derived metadata); the EDR members come only from plugin hook contributions, and `data_queries` only appears when a plugin describes some |
| `validate_response("exception", ..., document="common")`                                          | The 404 body satisfied EDR's `exception` schema (`code`) but not Common Part 1's RFC 7807 shape (`type` required)                                                                                            | `ogc_exception()` carries both shapes (`type`/`status`/`detail` plus `code`/`description`) — both schemas allow additional members                                                                                    |

One divergence between the standards surfaced by the Common validation:
the Common/Features `extent.spatial.crs` only allows CRS84 URIs, while
EDR's extent schema loosens it to any CRS string (e.g. `EPSG:4326`, which
EDR's metadata machinery emits). Collections contributed by the EDR plugin
follow EDR's reading; the stub plugin in core's tests uses the CRS84 URI so
core validates against the stricter Common schema.

## TeamEngine quirks worth knowing

Hard-won debugging knowledge baked into `xpublish_ogc_core.teamengine`:

- The REST API requires basic auth; the `ogccite` images ship a default
  `ogctest:ogctest` user.
- URI-valued test run properties (e.g. `iut`) must **not** end with a
  trailing slash — the suites concatenate paths like `/collections` directly
  onto them, and `//collections` is a 404.
- The EDR suite reports a missing `apiDefinition` argument with a misleading
  `Absolute URI is required, but received` error. It does not mean `iut` was
  mangled; pass `apiDefinition=<iut>/openapi.json`.
