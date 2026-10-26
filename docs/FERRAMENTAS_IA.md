# Ferramentas de IA do projeto: graphify e ponytail

Guia rápido das duas ferramentas usadas com o Claude Code neste repositório.

## graphify: mapa do código

O graphify transforma o repositório num grafo de conhecimento (funções, módulos, quem chama quem).
Com isso o Claude consulta o mapa em vez de ler arquivo por arquivo, gastando menos tokens e
achando mais rápido onde mexer.

### O que já está no repositório

- `.claude/skills/graphify/`: a skill do Claude Code (comando `/graphify`).
- `.claude/settings.json`: hooks que lembram o Claude de consultar o grafo antes de buscar no código.
- `CLAUDE.md` e `.claude/CLAUDE.md`: regras de uso do grafo para o Claude.
- `graphify-out/`: o grafo já gerado (`graph.json`, `graph.html`, `GRAPH_REPORT.md`).

### Instalação no PC (uma vez)

Os hooks chamam o comando `graphify`, então ele precisa estar instalado no PC:

```powershell
pip install graphifyy        # ou: uv tool install graphifyy
graphify --help              # confere a instalação
```

O pacote se chama `graphifyy` (com dois "y"), mas o comando é `graphify`.

### Comandos no terminal

| Comando | Para que serve |
|---|---|
| `graphify update .` | Reconstrói o grafo do código depois de mudanças. Não usa IA nem custa nada. |
| `graphify query "como funciona o upload?"` | Busca no grafo os trechos ligados a uma pergunta. |
| `graphify explain "salvar_estado"` | Explica um item do código e com o que ele se conecta. |
| `graphify path "pipeline_principal" "enviar_afd_para_servidor"` | Mostra o caminho entre dois itens. |
| `graphify watch .` | Fica observando a pasta e atualiza o grafo sozinho. |

Para ver o mapa, abra `graphify-out/graph.html` no navegador.
O resumo da arquitetura está em `graphify-out/GRAPH_REPORT.md`.

### Comandos dentro do Claude Code

| Comando | Para que serve |
|---|---|
| `/graphify .` | Gera o grafo completo. Também lê documentos e imagens, e para isso usa IA. |
| `/graphify --update` | Atualiza o grafo depois de mudar documentos. |

No dia a dia você não precisa chamar nada: o `CLAUDE.md` já instrui o Claude a usar o grafo.

## ponytail: menos código, mais revisão

O ponytail é um plugin que faz o Claude escrever só o código necessário: antes de criar algo,
ele verifica se já existe no projeto, na biblioteca padrão ou em uma dependência instalada.
Ele não corta validação, tratamento de erro nem segurança.

### Instalação no PC (uma vez)

Abra o Claude Code dentro desta pasta e rode, um de cada vez:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Precisa do Node.js instalado (`node --version`), porque o plugin usa dois hooks em Node.
Instale apenas a partir de `DietrichGebert/ponytail`: o projeto oficial não distribui `.exe` nem `.dll`.

### Comandos dentro do Claude Code

| Comando | Para que serve |
|---|---|
| `/ponytail` | Liga o ponytail ou mostra o nível atual. |
| `/ponytail lite`, `full`, `ultra`, `off` | Muda a intensidade ou desliga. |
| `/ponytail-review` | Revisa suas mudanças: bugs, segurança, falta de testes, código sobrando. Aceita `uncommitted`, `staged`, `branch` ou o link de um PR. |
| `/ponytail-audit` | A mesma revisão para o repositório inteiro, em ordem de prioridade. |
| `/ponytail-debt` | Junta os comentários `shortcut:` (atalhos deixados para depois) numa lista. |
| `/ponytail-gain` | Mostra os números de economia medidos pelo projeto. |
| `/ponytail band` | Liga ou desliga a barra de custo acima do prompt. |
| `/ponytail-help` | Resumo dos comandos. |

## Sugestão de uso neste projeto

1. Antes de começar uma mudança, peça ao Claude algo como "use o graphify para achar onde o NSR é salvo".
2. Depois de mudar o código, rode `graphify update .` (ou deixe o Claude rodar).
3. Antes de abrir um PR, rode `/ponytail-review branch`.
4. De tempos em tempos, rode `/ponytail-audit` para ver o que mais ameaça a confiabilidade da coleta.

Fontes: [graphify](https://github.com/safishamsi/graphify), [ponytail](https://github.com/DietrichGebert/ponytail).
