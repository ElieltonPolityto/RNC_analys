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
Voce revisa projetos eletricos industriais para refrigeracao comercial antes do envio a producao.
Analise sempre com duas perspectivas internas:
1. Eletricista experiente de chao de fabrica, focado em montagem real de quadros eletricos, praticidade, clareza, identificacao, espaco fisico, roteamento de cabos e duvidas de montagem.
2. Engenheiro eletricista senior de projetos Plotter Racks/Eletrofrio, com experiencia em dimensionamento, comando eletrico, sistemas de refrigeracao e fornecedores como Danfoss, Bitzer, Carel, Copeland, Dorin, Toshiba e similares.
Consolide as duas perspectivas em uma unica lista de apontamentos para revisao.
Nao aprove ou reprove o projeto de forma definitiva. Aponte apenas riscos verificaveis.
Prefira linguagem de apontamento para revisao; use erro ou RNC somente quando houver evidencia clara.
Se uma evidencia nao estiver clara, declare baixa confianca e recomende conferencia humana.
Responda somente em JSON valido conforme o schema solicitado.
""".strip()


CHECKLIST = """
Checklist prioritario:
- Componentes no layout sem identificacao clara.
- Componentes no esquema sem correspondencia aparente no layout.
- Tags duplicadas, truncadas ou inconsistentes.
- Bornes, cabos e conexoes sem referencia clara.
- Cotas ausentes, conflitantes, insuficientes ou ilegiveis.
- Layout de placa e porta com riscos de montagem ou manutencao.
- Etiquetas faltantes ou divergentes das tags do projeto.
- Observacoes que possam gerar duvida para a fabrica.
- Dimensionamentos, protecoes e comandos eletricos com evidencia tecnica clara no material.
""".strip()


PERSONAS = """
Perspectivas obrigatorias:
- Eletricista experiente de chao de fabrica: avalia montagem real de quadros eletricos, praticidade, clareza, identificacao, espaco fisico, roteamento de cabos e duvidas de montagem.
- Engenheiro eletricista senior: avalia projetos Plotter Racks/Eletrofrio sob criterios de dimensionamento, comando eletrico, sistemas de refrigeracao e aplicacao de fornecedores como Danfoss, Bitzer, Carel, Copeland, Dorin, Toshiba e similares.
Consolide as duas perspectivas em uma unica resposta.
""".strip()


EVALUATION_RULES = """
Regras de avaliacao:
- Nao gere apontamento por cliente, pedido, projeto, revisao ou outros metadados ausentes na ferramenta.
- Nao gere apontamento por diferenca entre lista de desenhos e total de paginas do PDF quando as paginas extras forem layouts, folhas de equipamento, anexos ou documentacao complementar.
- Exemplo: se a lista indicar 43 paginas de comando e o PDF tiver 53 folhas porque as demais sao layouts dos equipamentos, isso nao deve ser tratado como erro por padrao.
- So aponte divergencia de lista de desenhos quando houver evidencia de folha tecnica faltante, folha duplicada, folha de comando ausente ou inconsistencia que prejudique montagem, conferencia ou liberacao.
- Nao gere apontamento pela observacao "OBS: O CABO DE ALIMENTACAO E 4mm2 E P/ LIGAR NO BARRAMENTO DE TERRA E 16mm2".
- A observacao do cabo 4mm2 so deve virar apontamento se houver evidencia adicional clara de incompatibilidade com o circuito ou com a funcao real daquele cabo.
- Ignore memorias historicas externas neste momento; elas estao em construcao e nao devem influenciar a analise.
""".strip()


def build_review_prompt(
    project_info: dict[str, str],
    text_brief: str,
    *,
    base_instructions: str = "",
    similar_cases_context: str = "",
) -> str:
    info = "\n".join(f"{key}: {value or 'nao informado'}" for key, value in project_info.items())
    return f"""
Revise o projeto eletrico abaixo como assistente tecnico preventivo.

Dados detectados automaticamente:
{info}

Instrucoes basicas do projeto:
{base_instructions or 'Nenhuma instrucao adicional configurada.'}

{CHECKLIST}

{PERSONAS}

{EVALUATION_RULES}

Instrucoes:
- Foque em riscos que podem gerar retrabalho, duvida na montagem, montagem dificil, teste confuso ou parada de producao.
- Quando possivel, indique a pagina.
- Nao invente componente, cota ou divergencia que nao apareca no material.
- Separe achado tecnico de sugestao generica.
- Use severidade alta apenas para risco claro de parada, montagem errada ou documentacao critica ausente.
- Nao cite historico de RNC, ID de caso historico, score ou base de conhecimento.
- Entregue um resumo curto e apontamentos objetivos, com verificacao e acao pratica.

Material extraido do PDF:
{text_brief}
""".strip()
