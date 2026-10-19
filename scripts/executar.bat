:: Executa o script Python principal do projeto de automação de ponto eletrônico via agendamento de tarefas Windows.
@echo off

pushd "%~dp0.." || exit /b 1
if not exist "venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado. Crie-o e instale requirements.txt.
    popd
    exit /b 1
)
"venv\Scripts\python.exe" main.py %*
set "exit_code=%errorlevel%"
popd
exit /b %exit_code%
