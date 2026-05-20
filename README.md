# RNC Analyst

Ferramenta local para revisar projetos eletricos antes da liberacao para producao.

O objetivo e ser simples: escolher um PDF, analisar o projeto e abrir um relatorio pronto para uso.

Este e o README principal do projeto. Use este arquivo como referencia unica de uso, configuracao e solucao de problemas.

## Arquivos De Execucao

Para uso normal no Windows, use este arquivo na pasta raiz:

```text
ABRIR_RNC_ANALYST.bat
```

Ele abre a interface desktop em PySide6 e tambem verifica as dependencias locais. Se tudo ja estiver instalado e atualizado, ele nao reinstala tudo de novo.

Para abrir pelo `.bat`, o computador precisa ter Python 3.11 ou superior instalado. Se o Python nao estiver instalado, estiver fora do PATH ou for antigo demais, o programa pode nao abrir corretamente. Nesses casos, use a versao em executavel descrita abaixo ou instale o Python 3.11+ marcando a opcao `Add python.exe to PATH`.

Para gerar uma versao distribuivel em executavel, use:

```text
GERAR_EXECUTAVEL.bat
```

Esse arquivo nao e para abrir o programa no dia a dia. Ele serve para criar:

```text
dist\RNC_Analyst\RNC_Analyst.exe
dist\RNC_Analyst_executavel.zip
```

O `RNC_Analyst.exe` nao fica na pasta raiz do projeto. Depois de gerar o executavel, abra esta pasta:

```text
dist\RNC_Analyst\
```

Dentro dela estara:

```text
RNC_Analyst.exe
```

Para levar para outro PC, use o `.zip` ou copie a pasta `dist\RNC_Analyst` inteira. Nao copie apenas o `.exe`, porque ele depende das pastas internas geradas junto. No outro PC, depois de extrair, abra `RNC_Analyst.exe`. Nessa versao empacotada, o outro PC nao precisa ter Python instalado.

## Fluxo Basico

1. Abra `ABRIR_RNC_ANALYST.bat`.
2. Clique em `Selecionar PDF`.
3. Escolha o projeto eletrico em PDF.
4. Selecione o `Modelo do equipamento`.
5. Se o projeto estiver fora do padrao e precisar de catalogos/manuais, marque `Projeto fora do padrao - consultar manuais`.
6. Clique em `Analisar projeto`.
7. Aguarde a barra de progresso chegar a 100%.
8. O PDF do relatorio abre automaticamente.
9. Se precisar, use os botoes `Abrir PDF`, `Abrir Excel` ou `Abrir pasta`.

Na aba `Historico`, use `Exportar Excel` para salvar uma planilha com os registros de analises ja executadas.

Nao e necessario preencher cliente, projeto, pedido, data, revisao ou usuario. O sistema tenta detectar o que for possivel automaticamente. O modelo do equipamento e obrigatorio porque define qual contexto tecnico sera usado pela IA.

## O Que A Ferramenta Gera

Cada analise gera tres arquivos locais:

- PDF: relatorio curto e operacional.
- Excel: tabela detalhada para filtro, auditoria e conferencia.
- Markdown: trilha tecnica em texto.

Os arquivos ficam em:

```text
RNC_analyst\reports\
```

## IA E Custo

O modelo padrao e:

```text
gpt-5-mini
```

Ele foi escolhido para reduzir custo por analise.

Para usar IA externa, crie o arquivo `.env` a partir de:

```text
RNC_analyst\.env.example
```

Depois preencha:

```text
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-5-mini
```

Se `OPENAI_API_KEY` nao estiver configurada, o programa roda uma pre-analise local sem chamar a OpenAI.

Para trocar o modelo, abra a aba `Configuracoes` e salve outro modelo OpenAI. Use modelos maiores somente quando precisar de uma revisao mais profunda.

## Como Garantir O Prompt Usado

Na aba `Configuracoes`, existe o botao:

```text
Ver prompt da proxima analise
```

Use assim:

1. Selecione primeiro um PDF na aba `Nova analise`.
2. Selecione o modelo do equipamento.
3. Va para `Configuracoes`.
4. Clique em `Ver prompt da proxima analise`.
5. Confira o texto que sera enviado para a IA.

Isso mostra o `SYSTEM INSTRUCTIONS` e o `USER PROMPT` efetivos antes da chamada de IA.

## Contexto Por Modelo

A pasta editavel de contexto fica em:

```text
RNC_analyst\llm_context\
```

Ela tambem e copiada para:

```text
dist\RNC_Analyst\llm_context\
```

Assim, e possivel editar o contexto tanto no projeto fonte quanto na versao distribuida em executavel.

O app monta o prompt de forma controlada:

- Sempre le `Geral.md`.
- Sempre le `skills.md`.
- Sempre le `FalsosPositivos.md`.
- Le apenas o markdown do modelo selecionado em `modelos\`.
- So le arquivos dentro de `tools\` quando o operador marca `Projeto fora do padrao - consultar manuais`.

Para alterar a lista de modelos, edite:

```text
RNC_analyst\llm_context\equipamentos.json
```

Cada modelo precisa ter:

```json
{
  "id": "cool_pack",
  "nome": "Cool Pack",
  "arquivo": "modelos/cool_pack.md"
}
```

Para criar um novo modelo:

1. Crie um arquivo em `RNC_analyst\llm_context\modelos\`.
2. Adicione uma entrada em `equipamentos.json`.
3. Use o `id` sem espacos e sem acentos.
4. Reabra o programa para carregar a nova lista.

Para manter falsos positivos, edite:

```text
RNC_analyst\llm_context\FalsosPositivos.md
```

Coloque ali modelos, componentes, observacoes e padroes internos que nao devem virar RNC ou ponto de melhoria. Esse arquivo e sempre consultado.

Para cadastrar catalogos/manuais, coloque o markdown em:

```text
RNC_analyst\llm_context\tools\
```

Depois registre o arquivo em:

```text
RNC_analyst\llm_context\tools\manifest.json
```

Exemplo:

```json
{
  "tools": [
    {
      "id": "disjuntores",
      "nome": "Catalogo de disjuntores",
      "arquivo": "disjuntores.md",
      "modelos": ["*"],
      "palavras_chave": ["disjuntor", "protecao"]
    }
  ]
}
```

Use `modelos: ["*"]` quando o manual vale para todos os modelos. Use ids especificos, como `cool_pack`, quando o manual vale apenas para alguns modelos. Se o botao de manuais estiver marcado e nenhum manual pertinente for encontrado, a analise e bloqueada para evitar uma revisao fora do padrao sem referencia.

## Como A Analise Deve Se Comportar

A analise usa duas perspectivas internas:

- Eletricista experiente de chao de fabrica, focado em montagem real, clareza, identificacao, espaco fisico e duvidas praticas.
- Engenheiro eletricista senior, focado em dimensionamento, comando eletrico, sistemas de refrigeracao e fornecedores como Danfoss, Bitzer, Carel, Copeland, Dorin e Toshiba.

O relatorio final deve ser direto, com:

- Resumo da analise.
- Apontamentos para revisao.
- Orientacao para producao.

A ferramenta deve evitar chamar tudo de erro. Ela deve apontar somente o que tiver evidencia util para revisao.

## Estrutura Das Pastas

```text
RNC Analyst\
  README.md
  ABRIR_RNC_ANALYST.bat
  GERAR_EXECUTAVEL.bat
  dist\
    RNC_Analyst\
      RNC_Analyst.exe
    RNC_Analyst_executavel.zip
  RNC_analyst\
    desktop_app.py
    requirements.txt
    .env.example
    llm_context\
      equipamentos.json
      Geral.md
      skills.md
      FalsosPositivos.md
      tools.md
      modelos\
      tools\
        manifest.json
    prompts\
      instrucoes_base.txt
    src\
      desktop_service.py
      analysis.py
      prompts.py
      report_writer.py
      pdf_tools.py
      database.py
    reports\
    uploads\
    data\
```

## Arquivos Que Nao Devem Ir Para O GitHub

Por seguranca, estes itens ficam fora do Git:

- `.env`
- PDFs de clientes
- arquivos em `uploads/`
- arquivos em `reports/`
- banco local em `data/`
- dependencias instaladas localmente
- arquivos gerados em `build/` e `dist/`

Nao coloque projetos reais de cliente no GitHub.

## Problemas Comuns

Se a janela nao abrir:

1. Feche qualquer RNC Analyst aberto.
2. Execute novamente `ABRIR_RNC_ANALYST.bat`.
3. Confira se o computador tem Python 3.11 ou superior instalado.
4. Se aparecer erro de dependencia, rode o `.bat` de novo com internet disponivel.
5. Se a janela fechar ou continuar falhando, envie o arquivo `rnc_analyst_launcher.log` que fica na pasta raiz.

Se for usar em um computador sem Python:

1. Use `dist\RNC_Analyst_executavel.zip`.
2. Extraia o ZIP no computador de destino.
3. Abra `RNC_Analyst.exe` dentro da pasta extraida.
4. Nao copie apenas o `.exe`; leve a pasta completa.

Se a IA estiver cara:

1. Use `gpt-5-mini`.
2. Evite modelos maiores para revisoes simples.
3. Sem `OPENAI_API_KEY`, a ferramenta roda apenas a pre-analise local.
