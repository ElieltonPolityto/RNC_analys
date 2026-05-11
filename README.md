# RNC Analyst

Ferramenta local para revisar projetos eletricos antes da liberacao para producao.

O objetivo e ser simples: escolher um PDF, analisar o projeto e abrir um relatorio pronto para uso.

Este e o README principal do projeto. Use este arquivo como referencia unica de uso, configuracao e solucao de problemas.

## Qual .bat Usar

Para uso normal no Windows, use somente este arquivo na pasta raiz:

```text
ABRIR_RNC_ANALYST.bat
```

Ele abre a interface principal desktop em PySide6 e tambem verifica as dependencias locais. Se tudo ja estiver instalado e atualizado, ele nao reinstala tudo de novo.

O arquivo abaixo existe apenas como fallback da interface antiga:

```text
RNC_analyst\FALLBACK_STREAMLIT_ANTIGO.bat
```

Use esse fallback somente se a interface principal nao abrir ou se voce precisar comparar o comportamento antigo.

## Fluxo Basico

1. Abra `ABRIR_RNC_ANALYST.bat`.
2. Clique em `Selecionar PDF`.
3. Escolha o projeto eletrico em PDF.
4. Clique em `Analisar projeto`.
5. Aguarde a barra de progresso chegar a 100%.
6. O PDF do relatorio abre automaticamente.
7. Se precisar, use os botoes `Abrir PDF`, `Abrir Excel` ou `Abrir pasta`.

Nao e necessario preencher cliente, projeto, pedido, data, revisao ou usuario. O sistema tenta detectar o que for possivel automaticamente.

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

Para trocar o modelo, abra a aba `Configuracoes` na interface nova e salve outro modelo OpenAI. Use modelos maiores somente quando precisar de uma revisao mais profunda.

## Como Garantir O Prompt Usado

Na aba `Configuracoes`, existe o botao:

```text
Ver prompt da proxima analise
```

Use assim:

1. Selecione primeiro um PDF na aba `Nova analise`.
2. Va para `Configuracoes`.
3. Clique em `Ver prompt da proxima analise`.
4. Confira o texto que sera enviado para a IA.

Isso mostra o `SYSTEM INSTRUCTIONS` e o `USER PROMPT` efetivos antes da chamada de IA.

## Como A Analise Deve Se Comportar

A analise usa duas perspectivas internas:

- Eletricista experiente de chao de fabrica, focado em montagem real, clareza, identificacao, espaco fisico e duvidas praticas.
- Engenheiro eletricista senior, focado em dimensionamento, comando eletrico, sistemas de refrigeracao e fornecedores como Danfoss, Bitzer, Carel, Copeland, Dorin e Toshiba.

O relatorio final deve ser direto, com:

- Resumo da analise.
- Apontamentos para revisao.
- Orientacao para producao.

A ferramenta deve evitar chamar tudo de erro. Ela deve apontar somente o que tiver evidencia util para revisao.

## Base RNC

A aba `Base RNC` continua existindo para manutencao futura.

Neste momento, a analise principal nao usa a base historica de RNC como referencia. O foco atual e o PDF do projeto e o prompt tecnico.

## Interface Antiga

A interface Streamlit antiga continua disponivel como fallback:

```text
RNC_analyst\FALLBACK_STREAMLIT_ANTIGO.bat
```

Use apenas se precisar comparar comportamento ou se a interface desktop nao abrir.

## Estrutura Das Pastas

```text
RNC Analyst\
  README.md
  ABRIR_RNC_ANALYST.bat
  RNC_analyst\
    FALLBACK_STREAMLIT_ANTIGO.bat
    desktop_app.py
    app.py
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

Nao coloque projetos reais de cliente no GitHub.

## Problemas Comuns

Se a janela nao abrir:

1. Feche qualquer RNC Analyst aberto.
2. Execute novamente `ABRIR_RNC_ANALYST.bat`.
3. Se aparecer erro de dependencia, rode o `.bat` de novo com internet disponivel.
4. Se a janela fechar ou continuar falhando, envie o arquivo `rnc_analyst_launcher.log` que fica na pasta raiz.

Se a tela antiga aparecer:

1. Feche a janela antiga.
2. Abra `ABRIR_RNC_ANALYST.bat`.
3. O arquivo `FALLBACK_STREAMLIT_ANTIGO.bat` e apenas fallback.

Se a IA estiver cara:

1. Use `gpt-5-mini`.
2. Evite modelos maiores para revisoes simples.
3. Sem `OPENAI_API_KEY`, a ferramenta roda apenas a pre-analise local.
