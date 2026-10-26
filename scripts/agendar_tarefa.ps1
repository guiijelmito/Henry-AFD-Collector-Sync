<#
Registra a coleta de ponto no Agendador de Tarefas do Windows.

Roda TODO DIA às 23:59. O próprio script só coleta quando chega o next_audit_at do
estado_ponto.json (ex.: sexta 23:59); nos outros dias termina em segundos sem abrir o
navegador. Se a coleta de sexta falhar ou o PC estiver desligado, ela acontece no dia
seguinte, começando de onde a última coleta parou, sem perder marcações.

Uso (PowerShell como administrador, na pasta do projeto):
    powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa.ps1
#>
param(
    [string]$NomeTarefa = "Coleta Ponto Eletronico",
    [string]$Horario = "23:59"
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

Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho `
    -Settings $config -Principal $principal -Force | Out-Null

Write-Host "Tarefa '$NomeTarefa' registrada: todo dia às $Horario, como $usuario."
Write-Host "Testar agora:  Start-ScheduledTask -TaskName '$NomeTarefa'"
Write-Host "Ver resultado: Get-ScheduledTaskInfo -TaskName '$NomeTarefa'  (LastTaskResult 0 = sucesso)"
Write-Host "Importante: deixe HEADLESS_MODE=true no .env, pois a tarefa roda sem tela."
