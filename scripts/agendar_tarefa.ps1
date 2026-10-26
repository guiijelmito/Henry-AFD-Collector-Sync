<#
Registra a coleta de ponto no Agendador de Tarefas do Windows.

Roda toda SEXTA às 00:00 e repete de hora em hora até o fim do dia.
O próprio script só coleta se a auditoria da semana ainda não foi enviada; depois do
envio, as repetições terminam em segundos sem abrir o navegador. Assim, uma falha
(relógio fora do ar, PC desligado à meia-noite) é tentada de novo ao longo da sexta.

Uso (PowerShell como administrador, na pasta do projeto):
    powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa.ps1
#>
param(
    [string]$NomeTarefa = "Coleta Ponto Eletronico",
    [string]$Horario = "00:00"
)

$ErrorActionPreference = "Stop"
$raiz = (Resolve-Path "$PSScriptRoot\..").Path
$logs = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# A saída do .bat vai para logs\agendador.log (útil quando o Python nem chega a iniciar)
$acao = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$raiz\executar.bat`" >> `"$logs\agendador.log`" 2>&1`"" `
    -WorkingDirectory $raiz

$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At $Horario
$gatilho.Repetition = (New-ScheduledTaskTrigger -Once -At $Horario `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Hours 23)).Repetition

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

Write-Host "Tarefa '$NomeTarefa' registrada: toda sexta a partir de $Horario, de hora em hora, como $usuario."
Write-Host "Testar agora:  Start-ScheduledTask -TaskName '$NomeTarefa'"
Write-Host "Ver resultado: Get-ScheduledTaskInfo -TaskName '$NomeTarefa'  (LastTaskResult 0 = sucesso)"
Write-Host "Importante: deixe HEADLESS_MODE=true no .env, pois a tarefa roda sem tela."
