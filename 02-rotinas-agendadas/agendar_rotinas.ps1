<#
.SYNOPSIS
    Registra no Agendador de Tarefas do Windows as rotinas do rotinas.json.

.DESCRIPTION
    Sem -Registrar, só mostra o que seria registrado: nada é gravado.
    Cada tarefa chama "python rotina.py <nome>". O comando, o tempo limite e as
    tentativas continuam no rotinas.json, então mudá-los não exige registrar de novo;
    só a agenda (intervalo, horário e dias) fica gravada na tarefa.

.EXAMPLE
    .\agendar_rotinas.ps1

.EXAMPLE
    .\agendar_rotinas.ps1 -Registrar -Python "C:\Python313\python.exe"
#>
param(
    [string] $Configuracao = (Join-Path $PSScriptRoot 'rotinas.json'),
    [string] $Python = 'python',
    [string] $PastaDoAgendador = '\Fintech Exemplo\',
    [switch] $Registrar
)

$ErrorActionPreference = 'Stop'
$diasDaSemana = @{
    seg = 'Monday'; ter = 'Tuesday'; qua = 'Wednesday'; qui = 'Thursday'
    sex = 'Friday'; sab = 'Saturday'; dom = 'Sunday'
}

function Ler-Campo($rotina, [string] $campo, $padrao) {
    if ($null -ne $rotina.$campo) { return $rotina.$campo }
    return $padrao
}

function Descrever-Agenda($rotina) {
    if ($rotina.intervalo_min) { return "a cada $($rotina.intervalo_min) min" }
    $dias = if ($rotina.dias) { $rotina.dias -join ', ' } else { 'todo dia' }
    return "$dias, às $($rotina.horario)"
}

function Criar-Gatilho($rotina) {
    if ($rotina.intervalo_min) {
        $intervalo = New-TimeSpan -Minutes $rotina.intervalo_min
        return New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval $intervalo
    }
    if ($rotina.dias) {
        $dias = foreach ($dia in $rotina.dias) { $diasDaSemana[$dia] }
        return New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dias -At $rotina.horario
    }
    return New-ScheduledTaskTrigger -Daily -At $rotina.horario
}

$rotinas = (Get-Content -LiteralPath $Configuracao -Raw -Encoding UTF8 | ConvertFrom-Json).rotinas
$executor = Join-Path $PSScriptRoot 'rotina.py'

foreach ($rotina in $rotinas) {
    $argumentos = '"{0}" {1}' -f $executor, $rotina.nome
    # Folga acima do pior caso do rotina.py (todas as tentativas e esperas); é só uma rede de segurança.
    $tentativas = Ler-Campo $rotina 'tentativas' 3
    $segundos = (Ler-Campo $rotina 'tempo_limite_s' 3600) * $tentativas +
        (Ler-Campo $rotina 'espera_s' 30) * [math]::Pow(2, $tentativas) + 300
    $limite = [TimeSpan]::FromSeconds($segundos)

    if (-not $Registrar) {
        "[simulação] $PastaDoAgendador$($rotina.nome)"
        "    quando:   $(Descrever-Agenda $rotina)"
        "    executa:  $Python $argumentos"
        "    pasta:    $PSScriptRoot"
        "    limite:   $([int]$limite.TotalMinutes) min; se a anterior ainda estiver rodando, não abre outra"
        continue
    }

    $tarefa = @{
        TaskPath    = $PastaDoAgendador
        TaskName    = $rotina.nome
        Description = $rotina.descricao
        Action      = New-ScheduledTaskAction -Execute $Python -Argument $argumentos -WorkingDirectory $PSScriptRoot
        Trigger     = Criar-Gatilho $rotina
        Settings    = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit $limite
    }
    Register-ScheduledTask @tarefa -Force | Out-Null
    "registrada: $PastaDoAgendador$($rotina.nome) ($(Descrever-Agenda $rotina))"
}

if (-not $Registrar) {
    ''
    'Nada foi gravado no Agendador. Para registrar de verdade, rode de novo com -Registrar.'
}
