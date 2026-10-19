# Diário do DevTools

## Escopo que não deve ser esquecido

O DevTools é uma ferramenta de teste manual. Os ajustes abaixo são exclusivos
desse fluxo e não devem ser levados para produção nem para um futuro merge em
`feat/melhorias-qualidade`, a menos que a usuária mude essa instrução:

- O terminal pede as datas inicial e final (`DD/MM/AAAA`), sem assumir que o
  início é o dia da execução. Os filtros enviam precisão de minuto, do início
  `00:00` ao fim `23:59`; datas finais anteriores são rejeitadas.
- O navegador fica visível sem pausas artificiais entre ações.
- A coleta manual pode rodar fora da sexta e fora da janela agendada.
- O upload é opcional e não avança a agenda de auditoria.
- `manual_date_range`, o argumento `intervalo_manual` e os overrides
  `headless`/`slow_mo_ms` nos extratores e no upload existem para sustentar o
  DevTools. Não os porte em um merge para a branch de melhorias/produção sem
  autorização específica.

Ao preparar um merge futuro, leia este diário e exclua o comportamento de teste
acima da rotina agendada. Preserve os valores padrão dos extratores e do upload;
somente o DevTools deve passar o intervalo manual, `headless=False` e `slow_mo=0`.

## Registro

### 2026-10-19

- DevTools solicita explicitamente as datas inicial e final, com intervalo de
  dias inclusivo e sem dependência da data de execução.
- Mantidos navegador visível e intervalo manual; atraso global de visualização
  será removido na revisão de 2026-10-19 abaixo.
- Adicionado teste de intervalo em dia útil; o pipeline agendado continua
  restrito à sexta e à agenda configurada.
- Isolado o trabalho sem commit na branch `test/devtools-data-hora` para separar
  a versão de experimentação da branch `feat/melhorias-qualidade`.

### 2026-10-19 — integridade do filtro

- A inspeção local encontrou dois arquivos V1 com intervalos nominais distintos,
  mas conteúdo byte a byte idêntico. Os registros de marcação tipo 3 cobriam
  13–19/10/2020, fora dos filtros solicitados para outubro de 2026. O arquivo
  V2 inspecionado não continha marcações AFD reconhecíveis.
- Os extratores agora conferem o valor que permaneceu nos campos de início e fim
  após o preenchimento e validam a faixa de datas das marcações baixadas. Uma
  discrepância causa falha antes do arquivo ser disponibilizado para upload.
- Essa validação de integridade pertence ao caminho comum dos extratores de
  data/hora; os prompts de datas, navegador visível e atraso continuam sendo
  exclusivos do DevTools.
- O campo mascarado interrompia o valor enviado com segundos em um prefixo como
  `12/10/2026 00:`. Os campos do relógio recebem dígitos em `DDMMAAHHMM` (por
  exemplo, `1210260000`); a máscara exibe e a validação exige `DD/MM/AA HH:MM`.
- Removida a compatibilidade de estado com cursores `last_nsr_*`/`ultimo_nsr`;
  nenhum NSR é lido, persistido ou usado como cursor da coleta.

### 2026-10-19 — pausa visual do DevTools

- Removido `slow_mo` e os atrasos fixos ao final de download/upload.
- A pausa entre preencher `#lblDataI` e `#lblDataF` foi posteriormente removida.
- O navegador segue visível no DevTools; os parâmetros padrão da rotina
  agendada continuam inalterados.

### 2026-10-19 — remoção da pausa entre campos

- Removida a pausa artificial entre `#lblDataI` e `#lblDataF`; não há pausa
  visual fixa em nenhum ponto do DevTools.

### 2026-10-19 — formatos AFD por unidade

- Separadas as validações de registros: V1 lê data e hora em campos fixos
  `DDMMYYYY`/`HHMM`; V2 lê timestamp ISO-8601 no próprio registro.
- Cada extrator chama apenas o validador correspondente ao layout de sua unidade.
