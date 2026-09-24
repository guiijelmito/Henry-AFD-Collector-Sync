@echo off
:: Navega automaticamente para a pasta onde este arquivo .bat está salvo
cd /d "%~dp0"

:: Ativa o ambiente virtual
call venv\Scripts\activate

:: Executa o script principal de extração/envio
python main.py

:: Aguarda a conclusão do script antes de continuar
pause

:: Desativa o ambiente (opcional, boa prática)
deactivate