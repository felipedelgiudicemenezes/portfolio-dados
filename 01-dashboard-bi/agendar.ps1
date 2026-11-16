<#
.SYNOPSIS
    Atualiza a dashboard a cada 5 minutos pelo Agendador de Tarefas do Windows.

.DESCRIPTION
    Por padrão é só uma simulação: mostra a tarefa que seria criada e não grava nada.
    Com -Registrar, cria (ou substitui) a tarefa no Agendador do usuário atual.

.PARAMETER Registrar
    Registra a tarefa de verdade. Sem ele, nada é gravado.

.PARAMETER Python
    Executável do Python. No Agendador, prefira o caminho completo; o pythonw.exe
    roda sem abrir janela a cada execução.

.EXAMPLE
    .\agendar.ps1
    Mostra o que seria registrado.

.EXAMPLE
    .\agendar.ps1 -Python "C:\Python313\pythonw.exe" -Registrar
    Registra a tarefa.

.NOTES
    Para remover: Unregister-ScheduledTask -TaskName "Fintech Exemplo - dashboard comercial"
#>
[CmdletBinding()]
param(
    [switch]$Registrar,
    [string]$Python = "python",
    [ValidateRange(1, 1440)][int]$Minutos = 5,
    [string]$Nome = "Fintech Exemplo - dashboard comercial"
)

$ErrorActionPreference = "Stop"
$pasta = $PSScriptRoot
$argumentos = '"' + (Join-Path $pasta "build.py") + '"'

Write-Host "Tarefa       : $Nome"
Write-Host "Comando      : $Python $argumentos"
Write-Host "Pasta        : $pasta"
Write-Host "Frequência   : a cada $Minutos minutos, a partir de agora, sem data para acabar"
Write-Host "Sobreposição : se a execução anterior ainda estiver rodando, a nova é pulada"

if (-not $Registrar) {
    Write-Host ""
    Write-Host "Simulação: nada foi registrado. Para registrar de verdade, rode de novo com -Registrar."
    return
}

$acao = New-ScheduledTaskAction -Execute $Python -Argument $argumentos -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $Minutos)
$ajustes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes $Minutos)
Register-ScheduledTask -TaskName $Nome -Action $acao -Trigger $gatilho -Settings $ajustes -Force `
    -Description "Gera saida/*.html da dashboard comercial (dados fictícios)." | Out-Null
Write-Host "Tarefa registrada. Para remover: Unregister-ScheduledTask -TaskName '$Nome' -Confirm:`$false"
