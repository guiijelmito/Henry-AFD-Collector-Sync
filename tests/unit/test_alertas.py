from datetime import datetime

from ponto_eletronico import alertas, config, relatorio


def execucao(status):
    return relatorio.Execucao(
        inicio=datetime(2026, 10, 30), unidades=[relatorio.ResultadoUnidade("V1", status)]
    )


def test_falha_vai_pelo_telegram_com_o_pdf(monkeypatch):
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(alertas, "_telegram", lambda m, c, a=None: enviados.append((m, a)))
    assert alertas.enviar_alerta(execucao(relatorio.FALHA), "r.pdf") == "telegram"
    assert enviados == [("sendMessage", None), ("sendDocument", "r.pdf")]


def test_telegram_fora_do_ar_cai_para_email(monkeypatch):
    def quebrado(*a):
        raise OSError("sem rede")

    emails = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.exemplo")
    monkeypatch.setattr(config, "EMAIL_ALERTA", "eu@exemplo")
    monkeypatch.setattr(alertas, "_telegram", quebrado)
    monkeypatch.setattr(alertas, "_email", lambda *a: emails.append(a[0]))
    assert alertas.enviar_alerta(execucao(relatorio.FALHA)) == "email"
    assert emails == ["FALHA na coleta de ponto"]


def test_sucesso_sem_aviso_quando_desligado(monkeypatch):
    monkeypatch.setattr(config, "ALERTAR_SUCESSO", False)
    assert alertas.enviar_alerta(execucao(relatorio.OK)) is None
