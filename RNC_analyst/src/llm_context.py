from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pdf_tools import normalize_text


CONTEXT_DIR_NAME = "llm_context"
EQUIPMENT_CATALOG = "equipamentos.json"
GENERAL_CONTEXT = "Geral.md"
SKILLS_CONTEXT = "skills.md"
FALSE_POSITIVES_CONTEXT = "FalsosPositivos.md"
TOOLS_CONTEXT = "tools.md"
TOOLS_DIR = "tools"
TOOLS_MANIFEST = "manifest.json"


@dataclass(frozen=True)
class EquipmentOption:
    id: str
    name: str
    file: str


@dataclass(frozen=True)
class AnalysisOptions:
    equipment_model: str
    use_tools: bool = False


@dataclass(frozen=True)
class ContextBundle:
    equipment: EquipmentOption
    instructions: str
    context_files: list[str]
    used_tools: bool


def load_equipment_options(base_dir: Path) -> list[EquipmentOption]:
    catalog_path = context_dir(base_dir) / EQUIPMENT_CATALOG
    if not catalog_path.exists():
        raise ValueError(f"Arquivo de equipamentos nao encontrado: {catalog_path}")
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Arquivo de equipamentos invalido: {catalog_path}") from exc

    options: list[EquipmentOption] = []
    seen: set[str] = set()
    for item in payload.get("equipamentos", []):
        option = EquipmentOption(
            id=str(item.get("id") or "").strip(),
            name=str(item.get("nome") or "").strip(),
            file=str(item.get("arquivo") or "").strip(),
        )
        if not option.id or not option.name or not option.file:
            raise ValueError("Cada equipamento precisa ter id, nome e arquivo.")
        if option.id in seen:
            raise ValueError(f"Equipamento duplicado no cadastro: {option.id}")
        resolved = resolve_context_file(base_dir, option.file)
        if not resolved.exists():
            raise ValueError(f"Arquivo de contexto nao encontrado: {resolved}")
        seen.add(option.id)
        options.append(option)
    if not options:
        raise ValueError("Nenhum equipamento cadastrado em equipamentos.json.")
    return options


def build_context_bundle(
    *,
    base_dir: Path,
    options: AnalysisOptions,
    pdf_summary: dict[str, Any],
    legacy_prompt_path: Path | None = None,
) -> ContextBundle:
    equipment = find_equipment(base_dir, options.equipment_model)
    sections: list[tuple[str, str]] = []
    context_files: list[str] = []

    general_path = context_dir(base_dir) / GENERAL_CONTEXT
    if general_path.exists():
        add_section(sections, context_files, base_dir, general_path, GENERAL_CONTEXT)
    elif legacy_prompt_path is not None and legacy_prompt_path.exists():
        add_section(sections, context_files, base_dir, legacy_prompt_path, GENERAL_CONTEXT)
    else:
        raise ValueError("Contexto geral nao encontrado. Crie llm_context/Geral.md.")

    for required_file in [SKILLS_CONTEXT, FALSE_POSITIVES_CONTEXT, equipment.file]:
        resolved = resolve_context_file(base_dir, required_file)
        add_section(sections, context_files, base_dir, resolved, required_file)

    used_tools = False
    if options.use_tools:
        tool_policy_path = context_dir(base_dir) / TOOLS_CONTEXT
        if tool_policy_path.exists():
            add_section(sections, context_files, base_dir, tool_policy_path, TOOLS_CONTEXT)
        selected_tools = select_tools(base_dir, equipment.id, pdf_summary)
        if not selected_tools:
            raise ValueError(
                "Nenhum manual pertinente foi encontrado para este modelo e PDF. "
                "Revise llm_context/tools/manifest.json ou desmarque a consulta de manuais."
            )
        for tool_path in selected_tools:
            add_section(sections, context_files, base_dir, tool_path, tool_path.name)
        used_tools = True

    instructions = render_sections(equipment, options.use_tools, sections, context_files)
    return ContextBundle(
        equipment=equipment,
        instructions=instructions,
        context_files=context_files,
        used_tools=used_tools,
    )


def context_dir(base_dir: Path) -> Path:
    return base_dir / CONTEXT_DIR_NAME


def find_equipment(base_dir: Path, equipment_model: str) -> EquipmentOption:
    requested = (equipment_model or "").strip()
    for option in load_equipment_options(base_dir):
        if option.id == requested:
            return option
    raise ValueError(f"Modelo de equipamento invalido: {requested or 'nao informado'}")


def select_tools(base_dir: Path, equipment_id: str, pdf_summary: dict[str, Any]) -> list[Path]:
    manifest_path = context_dir(base_dir) / TOOLS_DIR / TOOLS_MANIFEST
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest de tools invalido: {manifest_path}") from exc

    haystack = normalize_text(
        " ".join(
            [
                str(pdf_summary.get("file_name") or ""),
                str(pdf_summary.get("text") or ""),
                json.dumps(pdf_summary.get("inferred") or {}, ensure_ascii=False),
            ]
        )
    )
    selected: list[Path] = []
    for item in payload.get("tools", []):
        models = [str(value).strip() for value in item.get("modelos", [])]
        if models and "*" not in models and equipment_id not in models:
            continue
        keywords = [normalize_text(str(value)) for value in item.get("palavras_chave", []) if str(value).strip()]
        if keywords and not any(keyword in haystack for keyword in keywords):
            continue
        file_name = str(item.get("arquivo") or "").strip()
        if not file_name:
            continue
        selected.append(resolve_tools_file(base_dir, file_name))
    return selected


def resolve_context_file(base_dir: Path, relative_path: str) -> Path:
    root = context_dir(base_dir).resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Caminho de contexto fora da pasta permitida: {relative_path}")
    return target


def resolve_tools_file(base_dir: Path, relative_path: str) -> Path:
    root = (context_dir(base_dir) / TOOLS_DIR).resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Caminho de manual fora da pasta tools: {relative_path}")
    if not target.exists():
        raise ValueError(f"Manual cadastrado nao encontrado: {target}")
    return target


def add_section(
    sections: list[tuple[str, str]],
    context_files: list[str],
    base_dir: Path,
    path: Path,
    label: str,
) -> None:
    if not path.exists():
        raise ValueError(f"Arquivo de contexto nao encontrado: {path}")
    rel = display_path(base_dir, path)
    context_files.append(rel)
    sections.append((rel if label else rel, path.read_text(encoding="utf-8").strip()))


def display_path(base_dir: Path, path: Path) -> str:
    parts = list(path.parts)
    if CONTEXT_DIR_NAME in parts:
        return Path(*parts[parts.index(CONTEXT_DIR_NAME):]).as_posix()
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def render_sections(
    equipment: EquipmentOption,
    use_tools: bool,
    sections: list[tuple[str, str]],
    context_files: list[str],
) -> str:
    header = [
        "Contexto selecionado pelo app:",
        f"- Modelo do equipamento: {equipment.name}",
        f"- Consultar manuais: {'sim' if use_tools else 'nao'}",
        "- Arquivos de contexto:",
    ]
    header.extend(f"  - {path}" for path in context_files)
    body: list[str] = ["\n".join(header)]
    for label, content in sections:
        body.extend([f"## {label}", content or "(arquivo vazio)"])
    return "\n\n".join(body).strip()
