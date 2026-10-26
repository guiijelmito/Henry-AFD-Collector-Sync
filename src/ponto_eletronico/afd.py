"""Leitura do arquivo AFD baixado do relógio.

Cada linha começa com o NSR (9 dígitos) seguido do tipo do registro (1 dígito).
Tipo 1 é o cabeçalho e tipo 9 o trailer; os demais são marcações e eventos.
"""

from dataclasses import dataclass


@dataclass
class ResumoAfd:
    reconhecido: bool  # o arquivo tem ao menos uma linha no formato NSR + tipo
    nsrs: list[int]

    @property
    def ultimo_nsr(self):
        return max(self.nsrs, default=None)

    def novos_apos(self, nsr):
        return sum(1 for n in self.nsrs if n > nsr)


def analisar_afd(caminho):
    reconhecido = False
    nsrs = []
    with open(caminho, encoding="latin-1") as f:
        for linha in f:
            if len(linha) >= 10 and linha[:10].isdigit():
                reconhecido = True
                if linha[9] in "234567":
                    nsrs.append(int(linha[:9]))
    return ResumoAfd(reconhecido, nsrs)
