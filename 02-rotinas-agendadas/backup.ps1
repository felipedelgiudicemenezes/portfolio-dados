<#
.SYNOPSIS
    Compacta uma pasta num .zip com data e hora no nome e mantém só os N mais recentes.

.DESCRIPTION
    O zip é escrito primeiro como .parcial e só recebe o nome final quando termina:
    um backup interrompido nunca conta na retenção nem empurra um backup bom para fora.
    Com -WhatIf, só mostra o que faria (e não grava o log).

.EXAMPLE
    .\backup.ps1 -Origem C:\dados -Destino D:\backups -Manter 7

.EXAMPLE
    .\backup.ps1 -Origem C:\dados -Destino D:\backups -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $Origem,
    [Parameter(Mandatory)] [string] $Destino,
    [ValidateRange(1, 365)] [int] $Manter = 7,
    [string] $Log = (Join-Path $PSScriptRoot 'logs\backup.log')
)

$ErrorActionPreference = 'Stop'

function Escrever-Log([string] $Mensagem) {
    $linha = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Mensagem
    Write-Output $linha
    if ($WhatIfPreference) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Log) -WhatIf:$false | Out-Null
    Add-Content -LiteralPath $Log -Value $linha -Encoding UTF8 -WhatIf:$false
}

try {
    $Origem = (Resolve-Path -LiteralPath $Origem).ProviderPath
    $Destino = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destino)
    $nome = Split-Path -Leaf $Origem
    $zip = Join-Path $Destino ('{0}-{1:yyyy-MM-dd_HHmmss}.zip' -f $nome, (Get-Date))
    Escrever-Log "Backup de $Origem (ficam os $Manter mais recentes)."

    if ($PSCmdlet.ShouldProcess($zip, 'Criar backup')) {
        New-Item -ItemType Directory -Force -Path $Destino | Out-Null
        # Sem esta chave, o .NET Framework do PowerShell 5.1 grava "pasta\arquivo" no zip, e o unzip
        # fora do Windows lê a barra invertida como parte do nome.
        [AppContext]::SetSwitch('Switch.System.IO.Compression.ZipFile.UseBackslash', $false)
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $parcial = "$zip.parcial"
        [IO.Compression.ZipFile]::CreateFromDirectory($Origem, $parcial, [IO.Compression.CompressionLevel]::Optimal, $true)
        Move-Item -LiteralPath $parcial -Destination $zip
        Escrever-Log ('Criado: {0} ({1:N1} MB).' -f (Split-Path -Leaf $zip), ((Get-Item -LiteralPath $zip).Length / 1MB))
    }

    # O zip novo conta como um dos $Manter, inclusive na simulação, em que ele não chega a existir.
    $antigos = Get-ChildItem -LiteralPath $Destino -Filter "$nome-*.zip" -File -ErrorAction SilentlyContinue |
        Where-Object FullName -ne $zip | Sort-Object Name -Descending | Select-Object -Skip ($Manter - 1)
    foreach ($arquivo in $antigos) {
        if ($PSCmdlet.ShouldProcess($arquivo.FullName, 'Apagar backup antigo')) {
            Remove-Item -LiteralPath $arquivo.FullName
            Escrever-Log "Apagado pela retenção: $($arquivo.Name)."
        }
    }
    exit 0
}
catch {
    Escrever-Log "ERRO: $($_.Exception.Message)"
    exit 1
}
