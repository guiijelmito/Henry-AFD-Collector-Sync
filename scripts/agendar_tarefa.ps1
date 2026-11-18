<#
Registra a coleta de ponto no Agendador de Tarefas do Windows.

Roda TODO DIA às 08:30 e envia o dia anterior (00:00 a 23:59) de cada unidade. Se o PC
estiver desligado ou a execução falhar, os dias pendentes são enviados na próxima execução,
em ordem, sem nunca reenviar um dia já enviado (ver docs/REGRAS.md).

Uso (PowerShell como administrador, na pasta do projeto):
    powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa.ps1
#>
param(
    [string]$NomeTarefa = "Coleta Ponto Eletronico",
    [string]$Horario = "08:30"
)

$ErrorActionPreference = "Stop"
$raiz = (Resolve-Path "$PSScriptRoot\..").Path
$logs = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# A saída do .bat vai para logs\agendador.log (útil quando o Python nem chega a iniciar)
$acao = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$raiz\executar.bat`" >> `"$logs\agendador.log`" 2>&1`"" `
    -WorkingDirectory $raiz

$gatilho = New-ScheduledTaskTrigger -Daily -At $Horario

$config = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# S4U: roda mesmo sem ninguém logado e sem guardar senha do Windows
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType S4U -RunLevel Limited

try {
    Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho `
        -Settings $config -Principal $principal -Force -ErrorAction Stop | Out-Null
} catch {
    Write-Host "ERRO: a tarefa '$NomeTarefa' NÃO foi registrada: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Rode o PowerShell como administrador ou crie a tarefa pelo Agendador de Tarefas"
    Write-Host "marcando 'Executar estando o usuário conectado ou não'."
    exit 1
}

Write-Host "Tarefa '$NomeTarefa' registrada: todo dia às $Horario, como $usuario."
Write-Host "Testar agora:  Start-ScheduledTask -TaskName '$NomeTarefa'"
Write-Host "Ver resultado: Get-ScheduledTaskInfo -TaskName '$NomeTarefa'  (LastTaskResult 0 = sucesso)"
Write-Host "Importante: deixe HEADLESS_MODE=true no .env, pois a tarefa roda sem tela."
