# Regras da coleta de ponto

Este documento registra as regras de negócio da coleta e do envio do AFD ao painel.
Qualquer mudança de regra deve ser atualizada aqui e no `CHANGELOG.md` no mesmo PR.
Decisões de arquitetura ficam em `docs/adr/`.

## 1. Regra de ouro: um dia enviado nunca é enviado de novo

O painel **sobrescreve** os registros recebidos. Depois do envio, o responsável corrige
horários manualmente no painel. Se um dia fosse reenviado, essas correções seriam
perdidas. Por isso:

- cada dia é enviado **uma única vez** por unidade;
- antes de baixar qualquer dia, o programa confere no `estado_ponto.json` se aquele
  dia já foi enviado, e pula o dia se já foi;
- nenhum comando reenvia um dia já enviado. Para reenviar de propósito é preciso
  editar o estado à mão, sabendo que as correções daquele dia serão perdidas.

## 2. O que é enviado: o dia fechado

- A coleta roda **todo dia às 14:30** (Agendador de Tarefas do Windows), com o
  usuário conectado ou não. Ver [ADR 0002](adr/0002-horario-14h30.md).
- Cada execução envia o **dia anterior**, das 00:00 às 23:59.
- Um dia só é considerado fechado 2 minutos depois da meia-noite, para não pegar uma
  batida de 23:59 que o relógio ainda esteja gravando. O horário de 14:30 não muda
  isso: o dia de hoje nunca é enviado, só os dias anteriores.
- Cada dia vira um arquivo AFD próprio (`AFD_V1_2026-11-14_a_2026-11-14.txt`).
- Dia sem marcações (domingo, feriado) também é enviado e registrado.
- O relógio V1 sempre devolve, junto com o dia pedido, a primeira batida seguinte
  (pedindo 12/11, vem também a primeira batida de 13/11). Essa batida é descartada do
  arquivo do dia e registrada no log; ela é enviada no arquivo do dia dela. Só batidas
  **depois** do fim são descartadas: uma batida antes do início continua barrando o envio.
- Arquivo com batida fora do período não é baixado de novo, porque o resultado se repete.

## 3. Controle por unidade

V1 e V2 têm filas independentes no `estado_ponto.json`. Uma unidade nunca altera a
fila da outra. Se a V2 falhar, a V1 segue normalmente, e a V2 recupera os dias dela
na próxima execução.

| Chave | Significado |
|---|---|
| `ultimo_dia_vX` | último dia enviado pela coleta agendada; todos os dias até ele estão enviados |
| `dias_avulsos_vX` | dias enviados fora da fila (`--dia`/`--semana`) ou confirmados no painel |
| `dias_duvidosos_vX` | dias cujo envio ficou sem confirmação (ver seção 5) |
| `ultima_semana_vX` | coleta semanal antiga: domingo da última semana enviada (só leitura) |
| `semanas_avulsas_vX` | coleta semanal antiga: semanas enviadas com `--semana` (só leitura) |

Exemplo:

```json
{
    "ultimo_dia_v1": "2026-11-14",
    "ultimo_dia_v2": "2026-11-13",
    "dias_avulsos_v1": ["2026-11-03"],
    "dias_duvidosos_v2": ["2026-11-14"]
}
```

## 4. Recuperação de dias atrasados

Se o PC ficar desligado ou uma execução falhar, a próxima execução envia, **por
unidade e em ordem**, todos os dias fechados depois do `ultimo_dia_vX`:

- até `MAX_DIAS_POR_EXECUCAO` dias por execução (padrão 7); o resto fica para a próxima;
- um dia que já foi enviado por outro caminho (avulso ou pela coleta semanal antiga)
  é pulado, e a fila avança;
- sem nenhum registro da unidade, começa em ontem e não tenta adivinhar dias antigos.

Na troca da coleta semanal para a diária, o programa lê `ultima_semana_vX` e continua
no domingo seguinte ao sábado daquela semana. As semanas em `semanas_avulsas_vX`
continuam bloqueadas.

## 5. Confirmação do envio e o caso "duvidoso"

O dia só conta como enviado quando o painel responde **HTTP 200** ao
`POST /api/reg/upload`. Os outros resultados:

| Resultado | O que significa | O que o programa faz |
|---|---|---|
| Falha antes de clicar em Enviar (login, rede) | nada chegou ao painel | tenta de novo (até `TENTATIVAS`) |
| HTTP 4xx (ex.: 401 `relogar`) | o painel recusou, nada foi gravado | tenta de novo; se insistir, o dia fica para a próxima execução |
| Sem resposta ou HTTP 5xx | o arquivo **pode** ter sido gravado | **não tenta de novo**; marca o dia como duvidoso e alerta |

Um dia duvidoso **para a fila daquela unidade** até alguém conferir o painel. Enquanto
isso, toda execução termina com falha e alerta. A outra unidade não é afetada.

Para resolver, confira no painel se as marcações do dia chegaram e rode:

```bat
executar.bat --resolver-duvidoso 2026-11-14 --unidade V2 --esta-no-painel sim
executar.bat --resolver-duvidoso 2026-11-14 --unidade V2 --esta-no-painel nao
```

- `sim`: o dia passa a contar como enviado e nunca mais sobe.
- `nao`: o dia é liberado e será enviado na próxima execução.

Depois disso, os dias seguintes são recuperados normalmente (seção 4).

## 6. Envio manual de dias ou semanas

```bat
executar.bat --dia 2026-11-12
executar.bat --dia 2026-11-12 --dia 2026-11-13
executar.bat --semana 2026-11-08
```

- `--semana` envia os dias, de domingo a sábado, da semana que contém a data.
- Os dois respeitam a regra de ouro: cada unidade pula os dias que já enviou.
- Dias ainda não fechados (hoje ou no futuro) são ignorados.
- Não mexem na fila agendada (`ultimo_dia_vX`); os dias enviados vão para
  `dias_avulsos_vX`.

### Dias enviados à mão no painel

Se alguém enviar um dia direto pelo painel, registre isso no estado para que a
coleta nunca envie esse dia de novo:

```bat
executar.bat --marcar-enviado 2026-11-08 --marcar-enviado 2026-11-09 --unidade todas
```

`--unidade` aceita `V1`, `V2` ou `todas`. O dia vai para `dias_avulsos_vX`, e a fila
agendada passa por ele sem enviá-lo. O comando não baixa nem envia nada.

## 7. Falhas, código de saída e alertas

- Qualquer falha numa unidade termina a execução com código de saída 1.
- Cada execução com envio ou falha gera um relatório em `logs/relatorios/` (JSON e PDF).
- O alerta vai pelo bot do Telegram (gratuito), com e-mail SMTP como reserva.
- Execução sem dia pendente termina com código 0, sem relatório e sem alerta.

## 8. Histórico de decisões

| Data | Decisão |
|---|---|
| 26/10/2026 | Coleta por semanas fechadas, de domingo a sábado. |
| 12/11/2026 | Controle de envio por unidade com `--semana`, para evitar sobrescrita. |
| 14/11/2026 | O painel sobrescreve os registros e as correções manuais são feitas depois do envio: nenhum dia pode ser reenviado. |
| 14/11/2026 | A coleta passa a ser diária, às 00:05, enviando só o dia anterior (dia fechado). Ver [ADR 0001](adr/0001-coleta-diaria-sem-reenvio.md). |
| 14/11/2026 | O envio só conta com HTTP 200; sem resposta, o dia fica duvidoso e não é reenviado sem conferência. |
| 18/11/2026 | O horário da coleta diária passa de 00:05 para 14:30, com a tarefa rodando com o usuário conectado ou não. Ver [ADR 0002](adr/0002-horario-14h30.md). |
