"""Fluxo manual de desenvolvimento para testar coleta e upload de AFD.

Este comando chama os extratores diretamente, sem a janela semanal do pipeline
e sem avançar o cursor salvo. Use ``python devtools.py`` na raiz do projeto.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from datetime import time as datetime_time
from pathlib import Path

from .cloud import enviar_afd_para_servidor
from .extractors.henry_v1 import automatizar_download_afd_v1
from .extractors.henry_v2 import automatizar_download_afd_v2
from .logging_config import setup_logging
from .state_store import manual_date_range

Downloader = Callable[[], str | Path | None]
Uploader = Callable[[str, str], object]


def solicitar_intervalo_manual(
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], object] | None = None,
    agora: datetime | None = None,
) -> tuple[str, str]:
    """Pede datas inicial e final, incluindo o dia inteiro no intervalo."""
    read = input_fn or input
    write = output_fn or print
    current_time = agora or datetime.now().astimezone()
    if current_time.tzinfo is None:
        current_time = current_time.astimezone()

    while True:
        valor_inicio = read("Data inicial (DD/MM/AAAA): ").strip()
        try:
            dia_inicio = datetime.strptime(valor_inicio, "%d/%m/%Y").date()
        except ValueError:
            write("Data inicial inválida. Use o formato DD/MM/AAAA.")
            continue

        valor_final = read("Data final (DD/MM/AAAA): ").strip()
        try:
            dia_final = datetime.strptime(valor_final, "%d/%m/%Y").date()
        except ValueError:
            write("Data final inválida. Use o formato DD/MM/AAAA.")
            continue

        if dia_final < dia_inicio:
            write(
                "A data final não pode ser anterior à data inicial. Informe o intervalo novamente."
            )
            continue

        data_inicio = datetime.combine(
            dia_inicio,
            datetime_time.min,
            tzinfo=current_time.tzinfo,
        )
        data_final = datetime.combine(
            dia_final,
            datetime_time(23, 59, 59),
            tzinfo=current_time.tzinfo,
        )
        try:
            intervalo = manual_date_range(data_inicio, data_final)
        except ValueError as exc:
            write(str(exc))
            continue
        write(f"Intervalo selecionado: {intervalo[0]} -> {intervalo[1]}")
        return intervalo


def criar_downloaders(intervalo: tuple[str, str]) -> dict[str, Downloader]:
    """Cria extratores manuais visíveis, sem atraso entre ações do navegador."""
    return {
        "V1": lambda: automatizar_download_afd_v1(
            intervalo_manual=intervalo,
            headless=False,
            slow_mo_ms=0,
        ),
        "V2": lambda: automatizar_download_afd_v2(
            intervalo_manual=intervalo,
            headless=False,
            slow_mo_ms=0,
        ),
    }


def _enviar_afd_visivelmente(caminho: str, unidade: str) -> object:
    """Abre também o navegador de upload sem atrasos artificiais."""
    return enviar_afd_para_servidor(
        caminho,
        unidade=unidade,
        headless=False,
        slow_mo_ms=0,
    )


def selecionar_unidades(
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], object] | None = None,
) -> tuple[str, ...]:
    """Pede qual relógio coletar; zero cancela o fluxo."""
    read = input_fn or input
    write = output_fn or print
    choices = {"1": ("V1",), "2": ("V2",), "3": ("V1", "V2")}
    while True:
        write("\nColeta manual de AFD (ignora a janela semanal):")
        write("  1) Unidade V1\n  2) Unidade V2\n  3) Ambas\n  0) Sair")
        choice = read("Selecione: ").strip()
        if choice == "0":
            return ()
        if choice in choices:
            return choices[choice]
        write("Opção inválida. Escolha 0, 1, 2 ou 3.")


def confirmar_upload(
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], object] | None = None,
) -> bool:
    """Confirma upload explicitamente; qualquer resposta diferente de sim nega."""
    read = input_fn or input
    write = output_fn or print
    while True:
        answer = read("Enviar os arquivos baixados ao painel? [s/N]: ").strip().casefold()
        if answer in {"s", "sim", "y", "yes"}:
            return True
        if answer in {"", "n", "não", "nao", "no"}:
            return False
        write("Responda s ou n.")


def resumir_arquivo(caminho: str | Path) -> str:
    """Retorna tamanho e faixa de NSR sem imprimir os dados pessoais do AFD."""
    file_path = Path(caminho)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    nsrs = [
        int(match.group(1)) for line in text.splitlines() if (match := re.match(r"^(\d{9})", line))
    ]
    summary = f"{file_path.stat().st_size} bytes"
    if nsrs:
        summary += f" | {len(nsrs)} registros | NSR {min(nsrs):09d}-{max(nsrs):09d}"
    else:
        summary += " | nenhum registro reconhecido"
    return summary


def processar_unidades(
    unidades: Sequence[str],
    enviar: bool | None,
    downloaders: Mapping[str, Downloader] | None = None,
    uploader: Uploader | None = None,
    output_fn: Callable[[str], object] | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> dict[str, str]:
    """Baixa as unidades escolhidas e, se confirmado, envia arquivos válidos.

    Os erros são isolados por unidade para que uma falha da V1 não impeça o
    teste da V2. Esta função não registra nem avança estado/cursor de coleta.
    """
    write = output_fn or print
    if downloaders is None:
        intervalo = solicitar_intervalo_manual(input_fn, write)
        download_map = criar_downloaders(intervalo)
    else:
        download_map = downloaders
    upload_file = _enviar_afd_visivelmente if uploader is None else uploader
    results: dict[str, str] = {}
    ready: dict[str, str] = {}

    for unidade in unidades:
        try:
            caminho = download_map[unidade]()
            if not caminho or not Path(caminho).is_file():
                results[unidade] = "SEM_ARQUIVO"
                write(f"[{unidade}] Nenhum arquivo AFD foi gerado.")
                continue
            path_text = str(caminho)
            ready[unidade] = path_text
            results[unidade] = "BAIXADO"
            write(f"[{unidade}] {path_text} | {resumir_arquivo(path_text)}")
        except Exception as exc:  # isolando falhas do relógio para testar a outra unidade
            results[unidade] = "FALHA_DOWNLOAD"
            write(f"[{unidade}] Falha no download: {exc}")

    if ready and enviar is None:
        enviar = confirmar_upload(input_fn, write)

    if enviar:
        for unidade, path_text in ready.items():
            try:
                upload_file(path_text, unidade)
                results[unidade] = "ENVIADO"
                write(f"[{unidade}] Formulário de upload enviado.")
            except Exception as exc:
                results[unidade] = "FALHA_UPLOAD"
                write(f"[{unidade}] Falha no upload: {exc}")
    elif ready:
        write("Upload ignorado; os arquivos permanecem na pasta de downloads.")

    return results


def main() -> int:
    """Executa o menu manual sem alterar o agendamento do pipeline normal."""
    setup_logging()
    unidades = selecionar_unidades()
    if not unidades:
        print("Teste cancelado.")
        return 0

    print("\nIniciando downloads selecionados...")
    intervalo = solicitar_intervalo_manual()
    # Baixe primeiro para que a pergunta de upload se baseie nos arquivos gerados.
    results = processar_unidades(
        unidades,
        enviar=None,
        downloaders=criar_downloaders(intervalo),
    )
    return int(any(status.startswith("FALHA") for status in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
