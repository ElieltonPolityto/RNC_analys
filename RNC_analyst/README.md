# RNC Analyst

Assistente local para revisao preventiva de projetos eletricos antes do envio para producao.

O objetivo do sistema e apontar riscos que podem gerar RNC, como cotas ausentes, divergencias entre layout e diagrama, componentes sem identificacao, etiquetas faltantes e inconsistencias de documentacao.

## Como Rodar

1. Crie uma copia de `.env.example` chamada `.env`.
2. Preencha pelo menos uma chave de API, quando quiser usar IA externa.
3. Execute `iniciar_RNC_analyst.bat`.
4. Abra a interface no navegador, se ela nao abrir automaticamente.

Na primeira execucao, o `.bat` cria um ambiente virtual e instala as dependencias.

## Privacidade

Arquivos PDF, uploads, relatorios, banco local e `.env` ficam fora do Git por padrao. Nao suba projetos reais de cliente para o GitHub.

## Provedores

- OpenAI: caminho principal para PDF e visao.
- Anthropic: alternativa forte para analise documental.
- Groq: modo experimental/economico usando texto extraido no MVP.

Se nenhuma chave estiver configurada, o app gera uma pre-analise local baseada no texto extraido e nas paginas criticas.

## Estrutura

```text
app.py
iniciar_RNC_analyst.bat
requirements.txt
.env.example
src/
  analysis.py
  database.py
  pdf_tools.py
  prompts.py
  report_writer.py
  ai_providers/
    anthropic_provider.py
    groq_provider.py
    openai_provider.py
```

