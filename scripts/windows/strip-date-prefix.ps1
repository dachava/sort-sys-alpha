# One-time cleanup: strips the old "<YYYY-MM-DD>_" naming prefix (ADR 0010
# retired this as the default) from files already filed under it. Doesn't
# recover the original casing/spacing lost when the file was first
# slugified -- it only removes the date, leaving the hyphenated slug as-is.
#
# Usage:
#   .\strip-date-prefix.ps1 -Path "$HOME\Downloads\_Filed" -WhatIf   # preview, touches nothing
#   .\strip-date-prefix.ps1 -Path "$HOME\Downloads\_Filed"           # actually rename
#   .\strip-date-prefix.ps1 -Path "$HOME\Downloads\_Filed\Archives"  # just one folder
#
# Never overwrites: a name collision gets a "-2", "-3", ... suffix, same
# convention sort-sys-alpha's own mover uses -- never deletes anything.

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
$DatePrefixPattern = '^(?<date>\d{4}-\d{2}-\d{2})_(?<rest>.+)$'

function Get-UniqueTargetPath {
    param([string]$Directory, [string]$BaseName, [string]$Extension)

    $candidate = Join-Path $Directory "$BaseName$Extension"
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }
    $n = 2
    while ($true) {
        $candidate = Join-Path $Directory "$BaseName-$n$Extension"
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
        $n++
    }
}

$items = Get-ChildItem -LiteralPath $Path -Recurse -File

$renamed = 0
foreach ($item in $items) {
    if ($item.BaseName -notmatch $DatePrefixPattern) {
        continue
    }

    $newBaseName = $Matches.rest
    $targetPath = Get-UniqueTargetPath -Directory $item.DirectoryName -BaseName $newBaseName -Extension $item.Extension

    if ($PSCmdlet.ShouldProcess($item.FullName, "Rename to $(Split-Path -Leaf $targetPath)")) {
        Rename-Item -LiteralPath $item.FullName -NewName (Split-Path -Leaf $targetPath)
        $renamed++
    }
}

Write-Host "renamed $renamed file(s)."
