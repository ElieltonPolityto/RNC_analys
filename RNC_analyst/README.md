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

## Base Historica de RNC

O app possui uma base local para casos reais de projeto + RNC:

```text
knowledge_base/
  ID01/
    projeto.pdf
    rnc.pdf
    metadata.json
    observacoes.txt
  ID02/
    projeto.pdf
    rnc.pdf
    metadata.json
    observacoes.txt
```

Use uma subpasta por caso. O ID deve ser estavel (`ID01`, `ID02`, `ID03`) porque ele sera citado nos relatorios preventivos.

Depois de copiar sua base real para essa pasta, abra a aba `Base RNC` e clique em `Indexar base`. O sistema extrai texto dos arquivos suportados, grava um indice local no SQLite e usa os casos mais parecidos durante novas analises.

Arquivos reais dentro de `knowledge_base/` nao entram no Git. Apenas o README e o template `ID_TEMPLATE` sao versionados.

## Prompt Base

O arquivo `prompts/instrucoes_base.txt` contem as instrucoes operacionais fixas usadas nas chamadas de IA. Ele tambem pode ser editado na aba `Prompt` do app.

Cada analise grava o hash do prompt utilizado, permitindo rastrear quais instrucoes estavam vigentes quando o relatorio foi gerado.

## Modos De Analise

- OpenAI: usa a chave `OPENAI_API_KEY` configurada no arquivo `.env`.
- Modelo local: executa a pre-analise local sem chamar API externa.

Se nenhuma chave estiver configurada, o app gera uma pre-analise local baseada no texto extraido e nas paginas criticas.

## Estrutura

```text
app.py
iniciar_RNC_analyst.bat
requirements.txt
.env.example
src/
  analysis.py
  case_base.py
  database.py
  pdf_tools.py
  prompts.py
  report_writer.py
  ai_providers/
    anthropic_provider.py
    groq_provider.py
    openai_provider.py
```
