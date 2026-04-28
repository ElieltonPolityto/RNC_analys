from __future__ import annotations

RNC_REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "overall_risk": {"type": "string", "enum": ["baixo", "medio", "alto"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "severity": {"type": "string", "enum": ["baixa", "media", "alta"]},
                    "category": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "evidence": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "severity",
                    "category",
                    "page",
                    "evidence",
                    "recommendation",
                    "confidence",
                ],
            },
        },
    },
    "required": ["summary", "overall_risk", "findings"],
}


SYSTEM_INSTRUCTIONS = """
Voce e um revisor tecnico de projetos eletricos industriais.
Sua tarefa e procurar riscos que podem gerar RNC antes do envio a producao.
Nao aprove ou reprove o projeto de forma definitiva. Aponte riscos verificaveis.
Priorize problemas praticos para a montagem de paineis eletricos.
Se uma evidencia nao estiver clara, declare baixa confianca.
Responda somente em JSON valido conforme o schema solicitado.
""".strip()


CHECKLIST = """
Checklist prioritario:
- Campos de revisao, cliente, documento, pedido, tensao e folha.
- Paginas faltantes ou divergentes da lista de desenhos.
- Componentes no layout sem identificacao clara.
- Componentes no esquema sem correspondencia aparente no layout.
- Tags duplicadas, truncadas ou inconsistentes.
- Bornes, cabos e conexoes sem referencia clara.
- Cotas ausentes, conflitantes, insuficientes ou ilegiveis.
- Layout de placa e porta com riscos de montagem ou manutencao.
- Etiquetas faltantes ou divergentes das tags do projeto.
- Observacoes que possam gerar duvida para a fabrica.
""".strip()


def build_review_prompt(project_info: dict[str, str], text_brief: str) -> str:
    info = "\n".join(f"{key}: {value or 'nao informado'}" for key, value in project_info.items())
    return f"""
Revise o projeto eletrico abaixo como assistente preventivo de RNC.

Dados informados pelo usuario:
{info}

{CHECKLIST}

Instrucoes:
- Foque em riscos que podem gerar retrabalho, duvida na montagem ou parada de producao.
- Quando possivel, indique a pagina.
- Nao invente componente, cota ou divergencia que nao apareca no material.
- Separe achado tecnico de sugestao generica.
- Use severidade alta apenas para risco claro de parada, montagem errada ou documentacao critica ausente.

Material extraido do PDF:
{text_brief}
""".strip()

