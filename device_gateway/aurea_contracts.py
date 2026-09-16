"""Fixed ADA-DCC artifacts for the bedside lamp.

The JSON files in ``device_gateway/aurea`` are the reviewed source of truth.
This module only locates those files and performs the explicit runtime-value
materialization required by ADA-DCC v0.1, whose effect values are concrete
scalars rather than symbolic parameter references.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable

AUREA_ARTIFACT_ROOT = Path(__file__).with_name("aurea")
CAPABILITY_FILES: dict[str, str] = {
    "lamp.power_on": "lamp.power_on.ada-dcc.json",
    "lamp.power_off": "lamp.power_off.ada-dcc.json",
    "lamp.set_brightness": "lamp.set_brightness.ada-dcc.json",
    "lamp.set_color_temperature": "lamp.set_color_temperature.ada-dcc.json",
}


def capability_contract_path(capability_id: str) -> Path:
    try:
        return AUREA_ARTIFACT_ROOT / CAPABILITY_FILES[capability_id]
    except KeyError as exc:
        raise ValueError(f"unsupported lamp capability: {capability_id}") from exc


def load_contract_document(capability_id: str) -> dict[str, Any]:
    path = capability_contract_path(capability_id)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load fixed ADA-DCC {path.name}: {exc}") from exc
    if not isinstance(document, dict) or document.get("capability_id") != capability_id:
        raise ValueError(f"invalid fixed ADA-DCC {path.name}")
    return document


def materialize_contract_document(capability_id: str, parameters: dict[str, object]) -> dict[str, Any]:
    document = deepcopy(load_contract_document(capability_id))
    declared = document.get("parameters", [])
    if not isinstance(declared, list):
        raise ValueError("fixed ADA-DCC parameters must be an array")
    names = [item.get("name") for item in declared if isinstance(item, dict)]
    if set(parameters) != set(names):
        raise ValueError(f"parameters for {capability_id} must be exactly {names}; got {sorted(parameters)}")
    if len(names) == 1:
        field = names[0]
        value = parameters[field]
        if field == "power":
            template_value = document["effect_semantics"]["effects"][0]["value"]["value"]
            if value is not template_value:
                raise ValueError(
                    f"{capability_id} only authorizes power={template_value!r}"
                )
        for effect in document["effect_semantics"]["effects"]:
            if effect["state"]["path"] == field:
                effect["value"]["value"] = value
        for requirement in document["evidence_semantics"]["requirements"]:
            if requirement["predicate"]["state"]["path"] == field:
                requirement["predicate"]["expected"]["value"] = value
    return document


def load_fixed_contract(capability_id: str, parameters: dict[str, object], parser: Callable[[dict[str, Any]], Any] | None = None) -> Any:
    if parser is None:
        from aurea.core.ada_dcc import parse_ada_dcc_contract
        parser = parse_ada_dcc_contract
    return parser(materialize_contract_document(capability_id, parameters))
