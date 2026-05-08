# RNC Analyst

Aplicacao local para revisao preventiva de projetos eletricos industriais antes do envio para producao.

## Interface Recomendada

Use a nova interface desktop:

```text
iniciar_RNC_analyst.bat
```

Ela abre o app em PySide6. O fluxo principal e:

1. Selecionar PDF.
2. Conferir leitura automatica.
3. Clicar em `Analisar projeto`.
4. Acompanhar o progresso de 0% a 100%.
5. Abrir o PDF, Excel ou pasta de relatorios.

Nao ha campos obrigatorios para cliente, projeto, pedido, revisao, data ou usuario.

## Interface Antiga

O Streamlit continua como fallback temporario:

```text
iniciar_RNC_analyst_streamlit.bat
```

Use somente se precisar comparar ou contornar algum problema da interface desktop.

## Primeira Execucao

O launcher verifica as dependencias em:

```text
.packages_runtime\
```

Ele instala ou atualiza dependencias apenas quando:

- a pasta de dependencias ainda nao existe;
- o Python mudou de versao;
- o `requirements.txt` mudou;
- o PySide6 ainda nao esta instalado.

Se tudo estiver satisfeito, ele apenas inicia o app.

## Configuracao Da IA

Copie:

```text
.env.example
```

para:

```text
.env
```

Configure quando quiser usar OpenAI:

```text
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-5-mini
```

O modelo padrao e `gpt-5-mini` para reduzir custo.

Sem `OPENAI_API_KEY`, a aplicacao roda a pre-analise local automaticamente.

Na aba `Configuracoes`, voce pode trocar o modelo OpenAI. A tela principal mostra:

- `IA economica: gpt-5-mini`
- `IA avancada: <modelo>` quando outro modelo estiver configurado

## Prompt Efetivo

Para verificar o prompt antes de gastar uma chamada de IA:

1. Selecione um PDF.
2. Abra a aba `Configuracoes`.
3. Clique em `Ver prompt da proxima analise`.

O app mostra exatamente o `SYSTEM INSTRUCTIONS` e o `USER PROMPT` que serao enviados para o modelo.

O prompt base editavel fica em:

```text
prompts\instrucoes_base.txt
```

## Relatorios

A analise gera arquivos em:

```text
reports\
```

Saidas geradas:

- PDF: relatorio curto para uso operacional.
- Excel: dados estruturados para filtro e conferencia.
- Markdown: trilha tecnica para auditoria.

O PDF principal evita metricas internas e mantem o foco em:

- Resumo da analise.
- Apontamentos para revisao.
- Orientacao para producao.

## Base RNC

A estrutura da base historica continua preservada para uso futuro:

```text
knowledge_base\
  ID_TEMPLATE\
```

Neste momento, a analise principal nao busca casos historicos nem envia IDs de RNC para o prompt. A aba `Base RNC` fica como area de manutencao futura.

## Privacidade

Estes itens nao devem ser enviados ao GitHub:

- `.env`
- PDFs reais
- `uploads\`
- `reports\`
- `data\`
- `.packages\`
- `.packages_runtime\`

Nao suba documentos reais de cliente no GitHub.

## Estrutura Principal

```text
desktop_app.py
app.py
iniciar_RNC_analyst.bat
iniciar_RNC_analyst_streamlit.bat
requirements.txt
.env.example
prompts\
  instrucoes_base.txt
src\
  desktop_service.py
  analysis.py
  prompts.py
  report_writer.py
  pdf_tools.py
  database.py
  case_base.py
  vector_store.py
  ai_providers\
tests\
```

## Validacao Para Desenvolvimento

Com o runtime/dependencias configurados:

```powershell
python -m unittest discover -s tests
python -m py_compile desktop_app.py src\desktop_service.py src\prompts.py src\analysis.py src\report_writer.py
```

## Uso Rapido

Abra:

```text
iniciar_RNC_analyst.bat
```

Selecione um PDF e clique em:

```text
Analisar projeto
```
