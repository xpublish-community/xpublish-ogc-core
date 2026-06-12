# XPublish OGC Core

Enable Xpublish plugins that support various OGC standards to serve via fully OGC compliant routes.

This works by creating an `app_router` that restructures the Xpublish API around [OGC API - Common](https://ogcapi.ogc.org/common/) conventions, and registering new `hookspec`s that other OGC plugins (for example [xpublish-edr](https://github.com/xpublish-community/xpublish-edr)) implement to contribute their conformance classes, collection metadata, and data queries.

## Endpoints

| Path                           | Description                                                                                                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/`                            | Landing page with `self`, `service-desc` (`/openapi.json`), `service-doc` (`/docs`), `conformance`, and `data` links (including the `http://www.opengis.net/def/rel/ogc/1.0/...` link relations) |
| `/conformance`                 | OGC API - Common conformance classes, plus every class declared by plugins via the `ogc_conformance_classes` hook                                                                                |
| `/collections`                 | One collection per published dataset, built from dataset attributes plus plugin contributions                                                                                                    |
| `/collections/{collection_id}` | A single collection, with `data_queries` aggregated from the `ogc_collection_dataqueries` hook. Unknown ids return an OGC `exception` shaped 404                                                 |

If `xpublish-ogc-core` is installed it is loaded automatically through the `xpublish.plugin` entry point. The landing page title and description are configurable on the plugin, by instantiating it explicitly (note that passing `plugins` to `xpublish.Rest` disables entry point auto-loading, so list every plugin you want):

```python
import xpublish
from xpublish_edr import CfEdrPlugin
from xpublish_ogc_core import OgcCorePlugin

rest = xpublish.Rest(
    datasets,
    plugins={
        "ogc-core": OgcCorePlugin(title="My data server", description="..."),
        "edr": CfEdrPlugin(),
    },
)
```

## Hookspecs

Other OGC plugins implement these `hookspec`s (declared on `OgcPluginSpec`):

- `ogc_router(deps)` — return an `APIRouter` mounted at the application root, for OGC routes like `/collections/{collection_id}/position`.
- `ogc_conformance_classes()` — return a list of conformance class URIs (`http://www.opengis.net/spec/...`) to aggregate into `/conformance`.
- `ogc_collection_metadata(collection_id, ds)` — return a dict of collection members (`extent`, `parameter_names`, `crs`, `output_formats`, ...) merged into the collection objects served at `/collections` and `/collections/{collection_id}`.
- `ogc_collection_dataqueries(collection_id, ds)` — return a dict of [data query descriptions](https://docs.ogc.org/is/19-086r6/19-086r6.html#_df2c080b-949c-40c3-ad14-d20228270c2d) (`position`, `area`, `cube`, ...) merged into the collection's `data_queries`.

## Schema-driven development

Development on this plugin, and for other OGC plugins is driven by the official OGC schemas and test suites:

- The official OGC schemas are vendored under `src/xpublish_ogc_core/schemas/` so tests run offline (refresh with `uv run scripts/update_schemas.py`): the [OGC API - Common Part 1](https://schemas.opengis.net/ogcapi/common/part1/1.0/openapi/schemas/) building blocks plus the collections shapes from [OGC API - Features Part 1](https://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/) (the `"common"` document, which core's own responses validate against), and the bundled OpenAPI documents published by the [OGC API - EDR](https://github.com/opengeospatial/ogcapi-environmental-data-retrieval) and [OGC API - Tiles](https://github.com/opengeospatial/ogcapi-tiles) standards for the plugins implementing them.

- `xpublish_ogc_core.testing` is shipped with the package so downstream plugins can validate their own responses against the official component schemas (the `document` argument picks the schema set, defaulting to `"edr"`):

  ```python
  from xpublish_ogc_core.testing import validate_response

  validate_response("landingPage", client.get("/").json(), document="common")
  validate_response("collection", client.get("/collections/air").json())
  validate_response(
      "tileSet",
      client.get("/datasets/air/tiles/WebMercatorQuad").json(),
      document="tiles",
  )
  ```

  Validation failures raise with the jsonschema error messages, pointing at the exact spec violation.

- Plugins are also suggested to use [Schemathesis](https://schemathesis.readthedocs.io/en/stable/) for hypothesis testing their advertised endpoints. `xpublish_ogc_core.testing.bundled_schema()` helps with loading the schema and then hypothesis testing against the spec.

- `xpublish_ogc_core.teamengine` is also shipped to help facilitate other plugins testing with the OGC CITE test suites running in Docker.

  ```python
  from xpublish_ogc_core import teamengine

  with (
      teamengine.serve_app(rest.app) as app_url,
      teamengine.teamengine_container(
          "ogccite/ets-ogcapi-edr10:1.3-teamengine-6.0.0-RC2"
      ) as engine_url,
  ):
      result = teamengine.run_suite(
          engine_url,
          "ogcapi-edr10",
          {"iut": app_url, "apiDefinition": f"{app_url}/openapi.json"},
      )

  assert not result.failure_names(), result.summary()
  ```

## Development

Tests cover every endpoint against the vendored OGC schemas (using a stub OGC plugin to exercise the hook plumbing) and fuzz the API with [Schemathesis](https://schemathesis.readthedocs.io/) against the app's own OpenAPI description:

```shell
uv run pytest
```
