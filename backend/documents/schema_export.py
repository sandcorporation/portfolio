"""Write the block document JSON Schema that the frontend types are generated from.

uv run python -m documents.schema_export          # write /schema/document.schema.json
uv run python -m documents.schema_export --check  # exit 1 if the committed file is stale
"""

import json
import sys
from pathlib import Path

from pydantic.json_schema import GenerateJsonSchema
from pydantic_core import CoreSchema

from documents.blocks import Document

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "document.schema.json"


class _ModelTitlesOnly(GenerateJsonSchema):
    """Keep titles on models (they become TS type names) but not on every field."""

    def field_title_should_be_set(self, schema: CoreSchema) -> bool:
        return False


def render() -> str:
    schema = Document.model_json_schema(mode="validation", schema_generator=_ModelTitlesOnly)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    fresh = render()
    if "--check" in argv:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != fresh:
            print(f"{SCHEMA_PATH} is stale: run `make gen` and commit the result", file=sys.stderr)
            return 1
        return 0
    SCHEMA_PATH.write_text(fresh, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
