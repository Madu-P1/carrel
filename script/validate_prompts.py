#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "docs" / "prompts" / "catalog.json"
ALLOWED_CATEGORIES = {
    "ui_audit",
    "ux_flow",
    "frontend_perf",
    "backend_api",
    "database",
    "accessibility",
    "metrics",
    "ci",
    "code_review",
    "tests",
    "usability_analysis",
}
REQUIRED_PROMPT_FIELDS = {
    "id",
    "category",
    "intent",
    "inputs",
    "outputs",
    "success_criteria",
    "risks",
    "model_notes",
}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ValidationError(Exception):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc


def _require_non_empty_string(value: Any, field: str, prompt_id: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{prompt_id}: {field} must be a non-empty string")


def _require_string_list(value: Any, field: str, prompt_id: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{prompt_id}: {field} must be a non-empty list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"{prompt_id}: {field}[{index}] must be a non-empty string")


def _validate_inputs(value: Any, prompt_id: str) -> set[str]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{prompt_id}: inputs must be a non-empty list")

    keys: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(f"{prompt_id}: inputs[{index}] must be an object")
        key = item.get("key")
        _require_non_empty_string(key, f"inputs[{index}].key", prompt_id)
        if key in keys:
            raise ValidationError(f"{prompt_id}: duplicate input key {key}")
        keys.add(key)
        _require_non_empty_string(
            item.get("description"), f"inputs[{index}].description", prompt_id
        )
        if not isinstance(item.get("required"), bool):
            raise ValidationError(f"{prompt_id}: inputs[{index}].required must be boolean")
    return keys


def _validate_fixture(prompt: dict[str, Any], input_keys: set[str]) -> None:
    prompt_id = str(prompt["id"])
    fixture_ref = prompt.get("sample_fixture")
    if fixture_ref is None:
        return
    _require_non_empty_string(fixture_ref, "sample_fixture", prompt_id)
    fixture_path = (CATALOG_PATH.parent / str(fixture_ref)).resolve()
    try:
        fixture_path.relative_to(CATALOG_PATH.parent.resolve())
    except ValueError as exc:
        raise ValidationError(f"{prompt_id}: sample_fixture must stay under docs/prompts") from exc
    if not fixture_path.exists():
        raise ValidationError(f"{prompt_id}: sample_fixture does not exist: {fixture_ref}")
    fixture = _load_json(fixture_path)
    if not isinstance(fixture, dict):
        raise ValidationError(f"{prompt_id}: sample_fixture must be a JSON object")
    missing = sorted(input_keys - set(fixture))
    if missing:
        raise ValidationError(
            f"{prompt_id}: sample_fixture missing input keys: {', '.join(missing)}"
        )


def _validate_template(prompt: dict[str, Any], input_keys: set[str]) -> None:
    prompt_id = str(prompt["id"])
    template = prompt.get("template")
    if template is None:
        return
    _require_non_empty_string(template, "template", prompt_id)
    placeholders = set(PLACEHOLDER_RE.findall(str(template)))
    unknown = sorted(placeholders - input_keys)
    if unknown:
        raise ValidationError(
            f"{prompt_id}: template has unknown placeholders: {', '.join(unknown)}"
        )
    unused_required = sorted(
        str(item["key"])
        for item in prompt["inputs"]
        if item["required"] and str(item["key"]) not in placeholders
    )
    if unused_required:
        raise ValidationError(
            f"{prompt_id}: required inputs not referenced by template: {', '.join(unused_required)}"
        )


def _validate_output_shape(prompt: dict[str, Any], input_keys: set[str]) -> None:
    prompt_id = str(prompt["id"])
    shape = prompt.get("expected_output_shape")
    if shape is None:
        return
    if not isinstance(shape, dict):
        raise ValidationError(f"{prompt_id}: expected_output_shape must be an object")
    sections = shape.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValidationError(
            f"{prompt_id}: expected_output_shape.sections must be a non-empty list"
        )
    for index, section in enumerate(sections):
        if not isinstance(section, str) or not section.strip():
            raise ValidationError(
                f"{prompt_id}: expected_output_shape.sections[{index}] must be a non-empty string"
            )
    refs = shape.get("must_reference_inputs", [])
    if not isinstance(refs, list):
        raise ValidationError(
            f"{prompt_id}: expected_output_shape.must_reference_inputs must be a list"
        )
    unknown_refs = sorted(str(ref) for ref in refs if ref not in input_keys)
    if unknown_refs:
        raise ValidationError(
            f"{prompt_id}: expected_output_shape references unknown inputs: {', '.join(unknown_refs)}"
        )


def validate_catalog(catalog_path: Path = CATALOG_PATH) -> None:
    catalog = _load_json(catalog_path)
    if not isinstance(catalog, dict):
        raise ValidationError("catalog must be a JSON object")
    _require_non_empty_string(catalog.get("version"), "version", "catalog")
    prompts = catalog.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise ValidationError("catalog.prompts must be a non-empty list")

    ids: set[str] = set()
    categories: set[str] = set()
    for index, prompt in enumerate(prompts):
        if not isinstance(prompt, dict):
            raise ValidationError(f"prompts[{index}] must be an object")
        missing = sorted(REQUIRED_PROMPT_FIELDS - set(prompt))
        prompt_id = str(prompt.get("id", f"prompts[{index}]"))
        if missing:
            raise ValidationError(f"{prompt_id}: missing required fields: {', '.join(missing)}")
        _require_non_empty_string(prompt["id"], "id", prompt_id)
        if not ID_RE.match(str(prompt["id"])):
            raise ValidationError(f"{prompt_id}: id must match {ID_RE.pattern}")
        if prompt["id"] in ids:
            raise ValidationError(f"{prompt_id}: duplicate id")
        ids.add(str(prompt["id"]))

        category = prompt["category"]
        _require_non_empty_string(category, "category", prompt_id)
        if category not in ALLOWED_CATEGORIES:
            raise ValidationError(f"{prompt_id}: category {category!r} is not allowed")
        categories.add(str(category))

        _require_non_empty_string(prompt["intent"], "intent", prompt_id)
        input_keys = _validate_inputs(prompt["inputs"], prompt_id)
        for field in ("outputs", "success_criteria", "risks", "model_notes"):
            _require_string_list(prompt[field], field, prompt_id)
        _validate_template(prompt, input_keys)
        _validate_fixture(prompt, input_keys)
        _validate_output_shape(prompt, input_keys)

    missing_categories = sorted(ALLOWED_CATEGORIES - categories)
    if missing_categories:
        raise ValidationError(f"catalog is missing categories: {', '.join(missing_categories)}")


def main() -> int:
    try:
        validate_catalog()
    except ValidationError as exc:
        print(f"prompt validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"prompt validation passed: {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
