from datetime import date

from ponto_eletronico import estado

SEXTA = date(2026, 10, 30)


def test_coleta_liberada_a_partir_da_data_e_nao_so_no_dia():
    dados = {"next_date": "2026-10-30"}
    assert not estado.coleta_liberada(dados, "V1", date(2026, 10, 29))
    assert estado.coleta_liberada(dados, "V1", SEXTA)
    assert estado.coleta_liberada(dados, "V1", date(2026, 11, 2))


def test_sem_data_a_coleta_esta_liberada():
    assert estado.coleta_liberada({}, "V2", SEXTA)


def test_data_por_unidade_tem_prioridade_sobre_a_compartilhada():
    dados = {"next_date": "2026-10-30", "next_date_v2": "2026-11-06"}
    assert estado.coleta_liberada(dados, "V1", SEXTA)
    assert not estado.coleta_liberada(dados, "V2", SEXTA)


def test_janela_avanca_mantendo_o_dia_da_semana_mesmo_com_atraso():
    dados = {"next_date": "2026-10-30"}
    # Coleta atrasada no sábado: a próxima continua sendo sexta
    assert estado.avancar_janela(dados, "V1", date(2026, 10, 31)) == date(2026, 11, 6)
    # Muito atrasada (duas semanas): pula para a próxima sexta futura
    dados = {"next_date": "2026-10-16"}
    assert estado.avancar_janela(dados, "V1", SEXTA) == date(2026, 11, 6)


def test_salvar_e_carregar(tmp_path):
    arquivo = tmp_path / "estado.json"
    dados = {}
    estado.registrar_nsr(dados, "V1", 45222)
    estado.salvar(dados, arquivo)
    assert estado.carregar(arquivo) == {"last_nsr_v1": "000045222"}
    assert estado.ultimo_nsr(estado.carregar(arquivo), "V1") == 45222
    assert estado.ultimo_nsr({}, "V2") == 1153
