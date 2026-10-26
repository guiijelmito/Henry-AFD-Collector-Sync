:: Executa o script Python principal do projeto de automação de ponto eletrônico via agendamento de tarefas Windows.
@echo off
:: Acentos nos logs não quebram o console do Agendador de Tarefas
set "PYTHONUTF8=1"

pushd "%~dp0.." || exit /b 1
if not exist "venv\Scripts\python.exe" (
    echo %date% %time% Ambiente virtual nao encontrado. Crie-o e instale requirements.txt.
    popd
    exit /b 1
)
"venv\Scripts\python.exe" main.py %*
set "exit_code=%errorlevel%"
popd
exit /b %exit_code%
