## O que muda

<!-- Resumo da mudança e do motivo. -->

## Como foi testado

<!-- Testes automatizados e, se houver, execução no PC. -->

## Checklist

- [ ] `pytest` e `ruff check .` passando
- [ ] Nenhum dia já enviado pode ser reenviado ao painel
- [ ] O estado só avança depois do upload confirmado (HTTP 200)
- [ ] Falhas terminam com código de saída diferente de 0 e geram alerta
- [ ] Seletores do Playwright não foram alterados (ou o Gui aprovou)
- [ ] Nenhuma senha, token ou dado sensível no código, nos logs ou no commit
- [ ] `docs/REGRAS.md` atualizado se uma regra mudou
- [ ] `CHANGELOG.md` atualizado
- [ ] ADR criado em `docs/adr/` se houve decisão de arquitetura
