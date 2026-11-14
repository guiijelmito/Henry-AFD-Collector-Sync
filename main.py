"""Compatibilidade com a execução histórica via ``python main.py``.

Uso:
    python main.py                       # envia os dias fechados pendentes (agendamento)
    python main.py --dia 2026-11-12      # força um dia; unidade que já o enviou é pulada
    python main.py --semana 2026-11-08   # força os dias da semana (domingo a sábado)
    python main.py --resolver-duvidoso 2026-11-12 --unidade V1 --esta-no-painel sim

Regras completas em docs/REGRAS.md.
"""

import argparse
import sys
from datetime import date
from pathlib import Path


def _sim_ou_nao(valor: str) -> bool:
    texto = valor.strip().casefold()
    if texto in {"sim", "s"}:
        return True
    if texto in {"nao", "não", "n"}:
        return False
    raise argparse.ArgumentTypeError("use 'sim' ou 'nao'")


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coleta AFD dos relógios V1 e V2.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--dia",
        type=date.fromisoformat,
        action="append",
        help="dia (AAAA-MM-DD) a coletar e enviar; pode repetir. Dia já enviado é pulado",
    )
    grupo.add_argument(
        "--semana",
        type=date.fromisoformat,
        help="data (AAAA-MM-DD) dentro da semana; envia os dias ainda não enviados dela",
    )
    grupo.add_argument(
        "--resolver-duvidoso",
        type=date.fromisoformat,
        metavar="AAAA-MM-DD",
        help="resolve um dia com envio duvidoso depois de conferir o painel",
    )
    parser.add_argument("--unidade", choices=["V1", "V2"], help="unidade do dia duvidoso")
    parser.add_argument(
        "--esta-no-painel",
        type=_sim_ou_nao,
        help="'sim' se as marcações do dia estão no painel, 'nao' se não chegaram",
    )
    return parser


def main(argv=None) -> int:
    parser = _criar_parser()
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

    if args.resolver_duvidoso is not None:
        if args.unidade is None or args.esta_no_painel is None:
            parser.error("--resolver-duvidoso exige --unidade e --esta-no-painel")
        from ponto_eletronico import config
        from ponto_eletronico.state_store import resolve_doubtful_day

        try:
            resolve_doubtful_day(
                config.ARQUIVO_ESTADO,
                args.unidade.lower(),
                args.resolver_duvidoso,
                is_in_panel=args.esta_no_painel,
            )
        except ValueError as exc:
            print(f"Erro: {exc}")
            return 2
        if args.esta_no_painel:
            print(f"{args.resolver_duvidoso} da {args.unidade} marcado como enviado.")
        else:
            print(f"{args.resolver_duvidoso} da {args.unidade} liberado para novo envio.")
        return 0

    from ponto_eletronico.pipeline import dias_da_semana, pipeline_principal

    if args.semana is not None:
        return pipeline_principal(dias=dias_da_semana(args.semana))
    return pipeline_principal(dias=args.dia)


if __name__ == "__main__":
    raise SystemExit(main())
