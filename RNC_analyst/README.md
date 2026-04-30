# RNC Analyst

Assistente local para revisao preventiva de projetos eletricos antes do envio para producao.

O objetivo do sistema e apontar riscos que podem gerar RNC, como cotas ausentes, divergencias entre layout e diagrama, componentes sem identificacao, etiquetas faltantes e inconsistencias de documentacao.

## Como Rodar

1. Crie uma copia de `.env.example` chamada `.env`.
2. Preencha `OPENAI_API_KEY`, quando quiser usar IA externa.
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

Depois de copiar sua base real para essa pasta, abra ou recarregue o RNC Analyst. O sistema indexa automaticamente a pasta `knowledge_base`, extrai texto dos arquivos suportados, grava um indice local no SQLite e usa os casos mais parecidos durante novas analises.

Arquivos reais dentro de `knowledge_base/` nao entram no Git. Apenas o README e o template `ID_TEMPLATE` sao versionados.

## Como A Consulta Historica Funciona

Ao abrir o app, a base `knowledge_base/` e varrida automaticamente. Para cada pasta `IDxx`, o sistema:

1. Le `metadata.json`, `observacoes.txt`, PDFs, planilhas e textos suportados.
2. Grava o resumo tecnico no SQLite local em `data/rnc_analyst.db`.
3. Atualiza um indice vetorial ChromaDB em `data/chroma/`.
4. Na analise de um projeto novo, busca os casos historicos mais parecidos e anexa os resumos ao prompt enviado para a IA.

Se a busca vetorial nao estiver disponivel, o app continua funcionando com busca lexical no SQLite. Isso evita parar a operacao por falha de dependencia, token ou internet.

## Embeddings E Custo

Por padrao, o `.env.example` usa:

```text
EMBEDDING_PROVIDER=local_hash
```

Esse modo e gratuito, local e nao envia sua base historica para terceiros. Ele cria vetores por hashing de termos tecnicos, o que e suficiente como fallback robusto, mas menos semantico que um modelo dedicado.

Para usar Hugging Face Inference API, altere o `.env`:

```text
EMBEDDING_PROVIDER=huggingface
HUGGINGFACE_API_TOKEN=hf_seu_token
HUGGINGFACE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Nesse modo, os textos usados para indexacao e consulta sao enviados ao Hugging Face para gerar embeddings. Consulte limites e politica de custo da sua conta antes de usar com documentos de cliente.

Tokens da OpenAI sao consumidos somente quando voce escolhe `OpenAI` para gerar a analise final. A leitura da base local, o SQLite e o ChromaDB local nao consomem tokens da OpenAI. Se `EMBEDDING_PROVIDER=huggingface`, a etapa de embeddings consome a cota do Hugging Face, nao da OpenAI.

## Prompt Base

O arquivo `prompts/instrucoes_base.txt` contem as instrucoes operacionais fixas usadas nas chamadas de IA. Ele tambem pode ser editado na aba `Prompt` do app.

Cada analise grava o hash do prompt utilizado, permitindo rastrear quais instrucoes estavam vigentes quando o relatorio foi gerado.

## Modos De Analise

- OpenAI: usa a chave `OPENAI_API_KEY` configurada no arquivo `.env`.
- Modelo local: executa a pre-analise local sem chamar API externa.

Se nenhuma chave estiver configurada, o app gera uma pre-analise local baseada no texto extraido e nas paginas criticas.

O modelo padrao da OpenAI e `gpt-5.5`. No `.env`, use o ID exatamente assim:

```text
OPENAI_MODEL=gpt-5.5
```

## Relatorios

Cada analise gera tres saidas locais em `reports/`:

- PDF: relatorio direto para circular, anexar e arquivar.
- Excel: dados estruturados para filtros e indicadores.
- Markdown: versao tecnica em texto para auditoria e ajustes.

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
  vector_store.py
  ai_providers/
    openai_provider.py
    utils.py
```
