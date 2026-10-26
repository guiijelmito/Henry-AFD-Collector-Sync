# Graph Report - Henry-AFD-Collector-Sync  (2026-10-26)

## Corpus Check
- 19 files · ~3,702 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: .bat 2, .example 1, (none) 1)

## Summary
- 83 nodes · 147 edges · 11 communities (5 shown, 6 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 4 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d959b8b2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- logging_config.py
- Henry AFD Collector & Sync
- pipeline.py
- os
- graphify: mapa do código
- henry_v2.py
- CLAUDE.md
- .claude/CLAUDE.md

## God Nodes (most connected - your core abstractions)
1. `setup_logging()` - 10 edges
2. `capturar_screenshot()` - 10 edges
3. `enviar_afd_para_servidor()` - 7 edges
4. `automatizar_download_afd_v1()` - 7 edges
5. `automatizar_download_afd_v2()` - 7 edges
6. `Henry AFD Collector & Sync` - 7 edges
7. `pipeline_principal()` - 6 edges
8. `⚙️ Installation & Setup` - 6 edges
9. `ColorFormatter` - 5 edges
10. `configured_path()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `pipeline_principal()`  [INFERRED]
  main.py → src/ponto_eletronico/pipeline.py
- `pipeline_principal()` --indirect_call--> `automatizar_download_afd_v2()`  [INFERRED]
  src/ponto_eletronico/pipeline.py → src/ponto_eletronico/extractors/henry_v2.py
- `enviar_afd_para_servidor()` --calls--> `capturar_screenshot()`  [EXTRACTED]
  src/ponto_eletronico/cloud.py → src/ponto_eletronico/logging_config.py
- `automatizar_download_afd_v1()` --calls--> `capturar_screenshot()`  [EXTRACTED]
  src/ponto_eletronico/extractors/henry_v1.py → src/ponto_eletronico/logging_config.py
- `pipeline_principal()` --indirect_call--> `automatizar_download_afd_v1()`  [INFERRED]
  src/ponto_eletronico/pipeline.py → src/ponto_eletronico/extractors/henry_v1.py

## Import Cycles
- None detected.

## Communities (11 total, 6 thin omitted)

### Community 0 - "logging_config.py"
Cohesion: 0.18
Nodes (3): ColorFormatter, _log_uncaught(), setup_logging()

### Community 1 - "Henry AFD Collector & Sync"
Cohesion: 0.15
Nodes (12): 1. Clone the repository, 2. Create and activate a virtual environment, 3. Install dependencies, 4. Configure environment variables, 5. Initialize state file, Henry AFD Collector & Sync, ⚙️ Installation & Setup, 🚀 Key Features (+4 more)

### Community 2 - "pipeline.py"
Cohesion: 0.33
Nodes (6): enviar_afd_para_servidor(), automatizar_download_afd_v1(), carregar_estado(), salvar_estado(), pipeline_principal(), _processar_unidade()

### Community 4 - "graphify: mapa do código"
Cohesion: 0.18
Nodes (10): Comandos dentro do Claude Code, Comandos dentro do Claude Code, Comandos no terminal, Ferramentas de IA do projeto: graphify e ponytail, graphify: mapa do código, Instalação no PC (uma vez), Instalação no PC (uma vez), O que já está no repositório (+2 more)

### Community 5 - "henry_v2.py"
Cohesion: 0.43
Nodes (4): automatizar_download_afd_v2(), carregar_estado(), salvar_estado(), capturar_screenshot()

## Knowledge Gaps
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `setup_logging()` connect `logging_config.py` to `pipeline.py`, `os`, `henry_v2.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `capturar_screenshot()` connect `henry_v2.py` to `logging_config.py`, `cloud.py`, `pipeline.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._