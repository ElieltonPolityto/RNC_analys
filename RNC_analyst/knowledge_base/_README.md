# Base Local de Casos RNC

Esta pasta e a memoria tecnica local do RNC Analyst.

Coloque aqui os pares de projeto + RNC que ja ocorreram na fabrica. Estes arquivos podem conter dados de clientes e ficam ignorados pelo Git.

## Estrutura Recomendada

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

## Regras Praticas

- Use um ID estavel por caso: `ID01`, `ID02`, `ID03`.
- Mantenha um projeto e uma RNC por pasta.
- Se houver anexos relevantes, coloque na mesma pasta.
- Preencha o `metadata.json` sempre que possivel.
- Use `observacoes.txt` para explicar o que realmente gerou a RNC.
- Nao suba PDFs, DWGs, RNCs reais ou dados de cliente para o GitHub.

Depois de copiar os casos, abra a aba `Base RNC` no app e clique em `Indexar base`.
