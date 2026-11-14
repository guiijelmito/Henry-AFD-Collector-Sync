# ADR 0001: Coleta diária do dia fechado, sem reenvio de dias

- **Status:** aceito
- **Data:** 14/11/2026

## Contexto

A coleta enviava semanas fechadas (domingo a sábado). O painel **sobrescreve** os
registros recebidos, e os horários são corrigidos manualmente no painel depois do
envio. Um reenvio apaga essas correções. A coleta semanal também deixava os dados do
painel até 7 dias desatualizados, e uma falha só aparecia uma semana depois.

## Decisão

- Rodar todo dia às 00:05 e enviar só o dia anterior (00:00 a 23:59).
- Manter, por unidade, o registro dos dias enviados (`ultimo_dia_vX`,
  `dias_avulsos_vX`) e nunca reenviar um dia registrado.
- Considerar o envio confirmado só com HTTP 200 do painel em `POST /api/reg/upload`.
- Sem resposta ou com HTTP 5xx, marcar o dia como duvidoso (`dias_duvidosos_vX`), não
  tentar de novo e parar a fila da unidade até a conferência manual.

## Alternativas consideradas

- **Manter a coleta semanal:** dados menos atualizados e falhas descobertas tarde.
- **Reenviar quando houver dúvida:** simples, mas pode apagar correções manuais.
- **Usar o NSR como cursor:** o filtro dos relógios é por data e hora, e o V1 inclui
  o primeiro NSR depois da data final, então o dia é uma unidade de controle mais segura.

## Consequências

- Os dados do painel ficam atualizados todo dia, e uma falha aparece no dia seguinte.
- São mais uploads, então o alerta no Telegram é obrigatório.
- Um envio sem resposta exige uma ação manual (`--resolver-duvidoso`) antes de a
  unidade continuar.
- O estado semanal antigo é lido na migração, e nenhum dia já enviado volta a subir.
