# Falsos positivos

Este arquivo deve ser consultado em todas as analises.

Registre aqui tudo que nao deve ser tratado como RNC ou ponto de melhoria quando aparecer no projeto.

## Regras atuais

- Nao apontar diferenca entre quantidade de folhas de comando e quantidade total do PDF quando as paginas extras forem layouts, anexos, folhas de equipamento ou documentacao complementar.
- Nao gerar apontamento pela observacao `O CABO DE ALIMENTACAO E 4mm2 E P/ LIGAR NO BARRAMENTO DE TERRA E 16mm2`, salvo quando houver evidencia adicional clara de incompatibilidade.
- Nao apontar ausencia de cliente, pedido, projeto, revisao ou metadados quando esses dados nao estiverem claramente disponiveis no PDF.

## Como adicionar um falso positivo

Use entradas objetivas:

```text
## Nome curto do padrao
- Quando aparece: descreva o texto, componente, modelo ou situacao.
- Nao apontar porque: explique o padrao interno.
- Ainda apontar se: liste a condicao que transforma o caso em risco real.
```
