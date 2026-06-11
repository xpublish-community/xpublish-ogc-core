#!/usr/bin/env -S uv run --script
"""Refresh the vendored OGC schema bundles in ``src/xpublish_ogc_core/schemas/``.

The bundled documents are committed so tests can run offline; run this script
to pull the latest published artifacts from the official OGC repositories.

Usage::

    python scripts/update_schemas.py
"""

import json
import urllib.request
from pathlib import Path

SCHEMAS = {
    "ogcapi-environmental-data-retrieval-1-oas30.bundled.json": (
        "https://raw.githubusercontent.com/opengeospatial/"
        "ogcapi-environmental-data-retrieval/3450dab3d76ba756f557bbf45afc0f6a244b0800/"
        "ogcapi-environmental-data-retrieval-1-oas30.bundled.json"
    ),
    "ogcapi-tiles-1.bundled.json": (
        "https://schemas.opengis.net/ogcapi/tiles/part1/1.0/openapi/"
        "ogcapi-tiles-1.bundled.json"
    ),
}

SCHEMA_DIR = Path(__file__).parent.parent / "src" / "xpublish_ogc_core" / "schemas"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in SCHEMAS.items():
        print(f"Downloading {url}")
        with urllib.request.urlopen(url) as response:
            raw = response.read()

        document = json.loads(raw)
        if "components" not in document:
            raise ValueError(
                f"{filename} has no 'components' member; "
                "xpublish_ogc_core.testing relies on #/components/schemas refs",
            )

        target = SCHEMA_DIR / filename
        target.write_bytes(raw)
        print(f"Wrote {target} ({len(raw)} bytes, OpenAPI {document.get('openapi')})")


if __name__ == "__main__":
    main()
