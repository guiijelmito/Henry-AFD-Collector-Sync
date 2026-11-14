# Changelog

Mudanças relevantes do projeto. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/). As regras
completas ficam em `docs/REGRAS.md` e as decisões em `docs/adr/`.

## [Não lançado]

### Alterado
- A coleta passa a ser diária: cada execução envia o dia anterior (00:00 a 23:59),
  em vez da semana de domingo a sábado.
- `--semana` agora envia os dias da semana, um a um, pulando os dias já enviados.
- `MAX_SEMANAS_POR_EXECUCAO` foi trocado por `MAX_DIAS_POR_EXECUCAO` (padrão 7).

### Adicionado
- Registro de dias enviados por unidade (`ultimo_dia_vX`, `dias_avulsos_vX`): um dia
  enviado nunca é enviado de novo, porque o painel sobrescreve os registros.
- Confirmação do upload pela resposta HTTP do painel (`POST /api/reg/upload`).
- Dias com envio sem confirmação ficam em `dias_duvidosos_vX`, param a fila da unidade
  e geram alerta até serem resolvidos com `--resolver-duvidoso`.
- Opção `--dia AAAA-MM-DD` para enviar dias específicos.
- `docs/REGRAS.md` com as regras de negócio e o histórico de decisões.
- ADR 0001 (`docs/adr/`) sobre a coleta diária sem reenvio.
- Template de PR com checklist (`.github/pull_request_template.md`).

### Migração
- O estado semanal (`ultima_semana_vX`, `semanas_avulsas_vX`) é lido automaticamente:
  a coleta diária continua no domingo seguinte à última semana enviada, sem reenviar
  nenhum dia dela.
