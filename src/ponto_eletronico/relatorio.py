"""Relatório de cada execução: o que aconteceu em cada unidade, em JSON e em PDF.

O JSON serve para conferência automática; o PDF é para leitura humana e explica
cada falha em linguagem simples, com o que fazer a seguir.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from .afd_validation import AFDRangeValidationError
from .logging_config import LOG_DIR, LOG_FILE
from .state_store import StateIntegrityError

RELATORIOS_DIR = LOG_DIR / "relatorios"

OK = "OK"
FORA_DA_JANELA = "FORA_DA_JANELA"
FALHA = "FALHA"
FALHA_TAILSCALE = "FALHA_TAILSCALE"
STATUS_DE_FALHA = {FALHA, FALHA_TAILSCALE}

DESCRICAO_STATUS = {
    OK: "Coletado e enviado",
    FORA_DA_JANELA: "Fora da janela de coleta",
    FALHA: "FALHOU",
    FALHA_TAILSCALE: "FALHOU (Tailscale)",
}
COR_STATUS = {
    OK: (30, 130, 60),
    FORA_DA_JANELA: (110, 110, 110),
    FALHA: (190, 40, 40),
    FALHA_TAILSCALE: (190, 40, 40),
}


@dataclass
class ResultadoUnidade:
    unidade: str
    status: str = OK
    mensagem: str = ""
    o_que_fazer: str = ""
    erro_tecnico: str = ""
    etapa: str = ""
    arquivo: str = ""
    enviado: bool = False
    duracao_s: float = 0.0


@dataclass
class Execucao:
    inicio: datetime
    fim: datetime | None = None
    unidades: list[ResultadoUnidade] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    @property
    def houve_falha(self):
        return any(u.status in STATUS_DE_FALHA for u in self.unidades)

    @property
    def houve_coleta(self):
        return any(u.status != FORA_DA_JANELA for u in self.unidades)

    @property
    def status_geral(self):
        if self.houve_falha:
            return FALHA
        return OK if self.houve_coleta else FORA_DA_JANELA

    def resumo_texto(self):
        linhas = [f"Ponto eletrônico - {self.inicio:%d/%m/%Y %H:%M} - {self.status_geral}"]
        for u in self.unidades:
            linha = f"{u.unidade}: {DESCRICAO_STATUS[u.status]}"
            if u.mensagem:
                linha += f" - {u.mensagem}"
            linhas.append(linha)
            if u.o_que_fazer:
                linhas.append(f"  O que fazer: {u.o_que_fazer}")
        return "\n".join(linhas)


class ColetorDeAvisos(logging.Handler):
    """Guarda os avisos e erros emitidos durante a execução para o relatório."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.linhas = []
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record):
        # Só a primeira linha: o traceback completo fica no arquivo de log
        self.linhas.append(self.format(record).splitlines()[0])


class ArquivoInvalido(Exception):
    """O arquivo baixado não tem conteúdo utilizável."""


def interpretar_erro(exc, etapa, unidade):
    """Traduz uma exceção em (mensagem, o que fazer) para quem vai ler o relatório."""
    texto = f"{type(exc).__name__}: {exc}"
    rede = "pelo Tailscale" if unidade == "V2" else "pela rede local"

    if isinstance(exc, StateIntegrityError):
        return (
            "O arquivo estado_ponto.json está corrompido.",
            "Abra o estado_ponto.json e corrija as datas next_audit_at_v1/v2 "
            "(formato 2026-10-30T00:00:00-03:00) ou restaure um backup.",
        )
    if isinstance(exc, OSError) and "ausente" in texto:
        return (
            "Faltam configurações no arquivo .env.",
            f"Preencha no .env as variáveis citadas no erro: {exc}",
        )
    if isinstance(exc, ConnectionError) and unidade == "V2":
        return (
            "O relógio V2 não respondeu pelo Tailscale.",
            "Confira se o Tailscale está conectado neste PC e no galpão, se o IP_V2 do .env "
            "está correto e se o relógio está ligado.",
        )
    if isinstance(exc, AFDRangeValidationError):
        return (
            f"O AFD da {unidade} veio sem marcações da semana ou com marcações fora dela.",
            "Baixe o AFD manualmente no relógio pelo filtro de data/hora e confira o período.",
        )
    if etapa == "download":
        if "net::ERR" in texto or "Timeout" in texto:
            return (
                f"O relógio {unidade} não respondeu.",
                f"Confira se o relógio está ligado e acessível {rede}. "
                "Abra o IP do relógio no navegador para testar.",
            )
        if isinstance(exc, ArquivoInvalido):
            return (str(exc), "Baixe o AFD manualmente no relógio para conferir se ele tem dados.")
        return (
            f"Erro inesperado ao baixar o AFD do relógio {unidade}.",
            "Veja o print da tela no fim do relatório e o arquivo de log.",
        )
    if etapa == "upload":
        if "net::ERR" in texto:
            return (
                "Sem conexão com o servidor de upload.",
                "Confira a internet do PC e se o endereço SERVER_URL do .env abre no navegador.",
            )
        if "Timeout" in texto:
            return (
                "O painel do servidor não carregou a tempo.",
                "Teste o login no painel pelo navegador; usuário ou senha podem ter mudado.",
            )
        return (
            "Erro inesperado ao enviar o arquivo ao servidor.",
            "O arquivo baixado foi guardado e será reenviado na próxima execução.",
        )
    return (
        "Erro inesperado.",
        "Veja o arquivo de log para os detalhes técnicos.",
    )


def salvar_json(execucao, destino=None):
    destino = Path(destino or RELATORIOS_DIR / f"execucao_{execucao.inicio:%Y%m%d_%H%M%S}.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = asdict(execucao)
    dados["status_geral"] = execucao.status_geral
    destino.write_text(json.dumps(dados, indent=2, default=str, ensure_ascii=False), "utf-8")
    return destino


def _t(texto):
    # Fontes padrão do PDF só aceitam latin-1 (acentos do português ok)
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def gerar_pdf(execucao, destino=None):
    destino = Path(destino or RELATORIOS_DIR / f"execucao_{execucao.inicio:%Y%m%d_%H%M%S}.pdf")
    destino.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    largura = pdf.epw

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(largura, 10, _t("Relatório da coleta de ponto"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    fim = f" até {execucao.fim:%H:%M:%S}" if execucao.fim else ""
    pdf.cell(
        largura,
        6,
        _t(f"Execução de {execucao.inicio:%d/%m/%Y %H:%M:%S}{fim}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    geral = execucao.status_geral
    cor = COR_STATUS[geral]
    textos_gerais = {
        OK: "Tudo certo nesta execução.",
        FALHA: "Houve falha. Veja abaixo o que aconteceu e o que fazer.",
        FORA_DA_JANELA: "Nenhuma unidade estava na janela de coleta. Nada a fazer.",
    }
    pdf.set_fill_color(*cor)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(largura, 11, _t(f"  {textos_gerais[geral]}"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for u in execucao.unidades:
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(*COR_STATUS[u.status])
        pdf.cell(
            largura,
            8,
            _t(f"Unidade {u.unidade}: {DESCRICAO_STATUS[u.status]}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "", 10)
        linhas = []
        if u.mensagem:
            linhas.append(u.mensagem)
        if u.o_que_fazer:
            linhas.append(f"O que fazer: {u.o_que_fazer}")
        if u.arquivo:
            situacao = "enviado" if u.enviado else "não enviado"
            linhas.append(f"Arquivo: {Path(u.arquivo).name} ({situacao})")
        if u.duracao_s:
            linhas.append(f"Duração: {u.duracao_s:.0f}s")
        if u.erro_tecnico:
            linhas.append(f"Detalhe técnico ({u.etapa}): {u.erro_tecnico[:300]}")
        for linha in linhas:
            pdf.multi_cell(largura, 5.5, _t(linha), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    if execucao.avisos:
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(largura, 8, _t("Avisos e erros registrados"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("courier", "", 8)
        for aviso in execucao.avisos[-40:]:
            pdf.multi_cell(largura, 4, _t(aviso[:400]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(largura, 4, _t(f"Log completo: {LOG_FILE}"), new_x="LMARGIN", new_y="NEXT")

    for screenshot in execucao.screenshots:
        pdf.add_page()
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(
            largura,
            8,
            _t(f"Tela no momento da falha: {Path(screenshot).name}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        try:
            pdf.image(screenshot, w=largura, h=pdf.eph - 12, keep_aspect_ratio=True)
        except Exception as exc:
            pdf.set_font("helvetica", "", 9)
            pdf.multi_cell(largura, 5, _t(f"Não foi possível incluir a imagem: {exc}"))

    pdf.output(str(destino))
    return destino
