"""Envio do resumo da execução: Telegram (gratuito) e, como reserva, e-mail SMTP."""

import json
import logging
import smtplib
import urllib.request
import uuid
from email.message import EmailMessage
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


def _telegram(metodo, campos, arquivo=None):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"
    fronteira = uuid.uuid4().hex
    corpo = b""
    for nome, valor in campos.items():
        corpo += (
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'
        ).encode()
    if arquivo:
        corpo += (
            (
                f"--{fronteira}\r\nContent-Disposition: form-data; "
                f'name="document"; filename="{Path(arquivo).name}"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode()
            + Path(arquivo).read_bytes()
            + b"\r\n"
        )
    corpo += f"--{fronteira}--\r\n".encode()
    pedido = urllib.request.Request(
        url, data=corpo, headers={"Content-Type": f"multipart/form-data; boundary={fronteira}"}
    )
    # URL fixa https da API do Telegram
    with urllib.request.urlopen(pedido, timeout=30) as resposta:  # noqa: S310
        if not json.load(resposta).get("ok"):
            raise RuntimeError(f"Telegram recusou {metodo}")


def _email(assunto, texto, pdf):
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = config.SMTP_USUARIO
    msg["To"] = config.EMAIL_ALERTA
    msg.set_content(texto)
    if pdf:
        msg.add_attachment(
            Path(pdf).read_bytes(), maintype="application", subtype="pdf", filename=Path(pdf).name
        )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORTA, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USUARIO, config.SMTP_SENHA)
        smtp.send_message(msg)


def enviar_alerta(execucao, pdf=None):
    """Envia o resumo pelo Telegram; se não der, tenta e-mail. Nunca derruba a execução."""
    if execucao.houve_falha:
        assunto = "FALHA na coleta de ponto"
    elif config.ALERTAR_SUCESSO and execucao.houve_coleta:
        assunto = "Coleta de ponto concluída"
    else:
        return None

    texto = execucao.resumo_texto()

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            _telegram("sendMessage", {"chat_id": config.TELEGRAM_CHAT_ID, "text": texto})
            if pdf:
                _telegram("sendDocument", {"chat_id": config.TELEGRAM_CHAT_ID}, pdf)
            logger.info("Alerta enviado pelo Telegram")
            return "telegram"
        except Exception:
            logger.exception("Falha ao enviar alerta pelo Telegram; tentando e-mail")

    if config.SMTP_HOST and config.EMAIL_ALERTA:
        try:
            _email(assunto, texto, pdf)
            logger.info("Alerta enviado por e-mail para %s", config.EMAIL_ALERTA)
            return "email"
        except Exception:
            logger.exception("Falha ao enviar alerta por e-mail")

    logger.warning("Nenhum canal de alerta funcionou ou está configurado; veja o relatório local")
    return None
