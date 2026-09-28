:: Executa o script Python principal do projeto de automação de ponto eletrônico via agendamento de tarefas Windows.
@echo off

:: Muda o diretório para o local do projeto
cd /d "C:\Users\Leticia\Documents\Dev-Verth\Automações\ponto_eletronico_automazido"

:: Ativa o ambiente virtual do Python
call venv\Scripts\activate

python main.py

:: Exibe uma mensagem indicando que a execução foi concluída e fecha o terminal
echo Execução concluída. Verifique log_execucao.txt para detalhes. 
exit