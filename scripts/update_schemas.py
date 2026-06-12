#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["pyyaml"]
# ///
"""Refresh the vendored OGC schemas in ``src/xpublish_ogc_core/schemas/``.

Two kinds of artifacts are vendored, all committed so tests run offline:

- bundled OpenAPI documents published by individual OGC API standards
  (EDR, Tiles), validated through their ``#/components/schemas``;
- the standalone building-block schemas for OGC API - Common. Common
  Part 2 (Collections) has not been published, so the collections shapes
  come from OGC API - Features Part 1, which they derive from. The
  Features schemas are published as YAML and converted to JSON here, with
  their relative ``*.yaml`` refs rewritten to match; a ``manifest.json``
  records each file's source URL so ``xpublish_ogc_core.testing`` can
  resolve the relative refs offline.

Usage::

    uv run scripts/update_schemas.py
"""

import json
import urllib.request
from pathlib import Path
from typing import Any

import yaml

BUNDLES = {
    "ogcapi-environmental-data-retrieval-1-oas30.bundled.json": (
        "https://raw.githubusercontent.com/opengeospatial/"
        "ogcapi-environmental-data-retrieval/3450dab3d76ba756f557bbf45afc0f6a244b0800/"
        "ogcapi-environmental-data-retrieval-1-oas30.bundled.json"
    ),
    "ogcapi-tiles-1.bundled.json": (
        "https://schemas.opengis.net/ogcapi/tiles/part1/1.0/openapi/ogcapi-tiles-1.bundled.json"
    ),
}

COMMON_PART1 = "https://schemas.opengis.net/ogcapi/common/part1/1.0/openapi/schemas"
FEATURES_PART1 = "https://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas"

# local path under schemas/common/ -> source URL
COMMON_SOURCES = {
    "part1/landingPage.json": f"{COMMON_PART1}/landingPage.json",
    "part1/confClasses.json": f"{COMMON_PART1}/confClasses.json",
    "part1/exception.json": f"{COMMON_PART1}/exception.json",
    "part1/link.json": f"{COMMON_PART1}/link.json",
    "features/collections.json": f"{FEATURES_PART1}/collections.yaml",
    "features/collection.json": f"{FEATURES_PART1}/collection.yaml",
    "features/extent.json": f"{FEATURES_PART1}/extent.yaml",
    "features/link.json": f"{FEATURES_PART1}/link.yaml",
}

# component name -> local path, for xpublish_ogc_core.testing lookups
COMMON_COMPONENTS = {
    "landingPage": "part1/landingPage.json",
    "confClasses": "part1/confClasses.json",
    "exception": "part1/exception.json",
    "link": "part1/link.json",
    "collections": "features/collections.json",
    "collection": "features/collection.json",
    "extent": "features/extent.json",
}

SCHEMA_DIR = Path(__file__).parent.parent / "src" / "xpublish_ogc_core" / "schemas"


def rewrite_yaml_refs(node: Any) -> Any:
    """Point relative ``*.yaml`` refs at the converted ``*.json`` files."""
    if isinstance(node, dict):
        return {
            key: (
                value.replace(".yaml", ".json")
                if key == "$ref" and isinstance(value, str)
                else rewrite_yaml_refs(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [rewrite_yaml_refs(item) for item in node]
    return node


def update_bundles() -> None:
    for filename, url in BUNDLES.items():
        print(f"Downloading {url}")  # noqa: T201
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
        print(f"Wrote {target} ({len(raw)} bytes, OpenAPI {document.get('openapi')})")  # noqa: T201


def update_common() -> None:
    common_dir = SCHEMA_DIR / "common"

    for path, url in COMMON_SOURCES.items():
        print(f"Downloading {url}")  # noqa: T201
        with urllib.request.urlopen(url) as response:
            raw = response.read()

        if url.endswith(".yaml"):
            schema = rewrite_yaml_refs(yaml.safe_load(raw))
        else:
            schema = json.loads(raw)

        target = common_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {target}")  # noqa: T201

    manifest = {
        "components": COMMON_COMPONENTS,
        # registered URIs are the converted .json siblings of the sources,
        # so the rewritten relative refs resolve within the registry
        "resources": {path: url.replace(".yaml", ".json") for path, url in COMMON_SOURCES.items()},
    }
    manifest_path = common_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")  # noqa: T201


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    update_bundles()
    update_common()


if __name__ == "__main__":
    main()
