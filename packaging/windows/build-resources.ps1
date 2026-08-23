[CmdletBinding()]
param(
    [string]$OutputPath,

    [string]$VerifyAgainst
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ResourceSource = Join-Path $PSScriptRoot "axidev-osk-resources.rc"
if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot "axidev-osk-resources.dll"
}
$VsWhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $VsWhere -PathType Leaf)) {
    throw "Visual Studio Installer could not be found. Install Visual Studio Build Tools with the C++ build tools."
}

$VisualStudioPath = & $VsWhere `
    -latest `
    -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $VisualStudioPath) {
    throw "Visual Studio C++ build tools could not be found."
}

$ToolsetRoot = Join-Path $VisualStudioPath "VC\Tools\MSVC"
$Toolset = Get-ChildItem -LiteralPath $ToolsetRoot -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "bin\Hostx64\x64\link.exe") } |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if ($null -eq $Toolset) {
    throw "The 64-bit Microsoft linker could not be found."
}

$Link = Join-Path $Toolset.FullName "bin\Hostx64\x64\link.exe"
$Dumpbin = Join-Path $Toolset.FullName "bin\Hostx64\x64\dumpbin.exe"
$WindowsSdkBin = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$WindowsSdk = Get-ChildItem -LiteralPath $WindowsSdkBin -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "x64\rc.exe") } |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if ($null -eq $WindowsSdk) {
    throw "A Windows 10 or Windows 11 SDK resource compiler could not be found."
}
$ResourceCompiler = Join-Path $WindowsSdk.FullName "x64\rc.exe"

function Assert-ResourceOnlyDll([string]$Path) {
    $headers = & $Dumpbin /headers $Path | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "dumpbin could not inspect $Path."
    }
    if ($headers -notmatch "(?im)^\s*0+\s+entry point") {
        throw "$Path has a nonzero entry point."
    }
    if ($headers -match "(?im)^\s*\.text\s+name") {
        throw "$Path contains executable code."
    }
}

if (-not ([System.Management.Automation.PSTypeName]"AxidevResourceStrings").Type) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class AxidevResourceStrings
{
    private const uint LOAD_LIBRARY_AS_DATAFILE = 0x00000002;
    private const uint LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryEx(string fileName, IntPtr file, uint flags);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int LoadString(IntPtr module, uint id, StringBuilder value, int capacity);

    [DllImport("kernel32.dll")]
    private static extern bool FreeLibrary(IntPtr module);

    public static string Read(string path, uint id)
    {
        IntPtr module = LoadLibraryEx(
            path,
            IntPtr.Zero,
            LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE);
        if (module == IntPtr.Zero)
            throw new Win32Exception(Marshal.GetLastWin32Error());

        try
        {
            StringBuilder value = new StringBuilder(1024);
            int length = LoadString(module, id, value, value.Capacity);
            if (length == 0)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return value.ToString();
        }
        finally
        {
            FreeLibrary(module);
        }
    }
}
"@
}

function Read-ExpectedStrings {
    $strings = @{}
    foreach ($line in Get-Content -LiteralPath $ResourceSource) {
        if ($line -match '^\s*(\d+)\s+"([^"]*)"\s*$') {
            $strings[[int]$Matches[1]] = $Matches[2]
        }
    }
    foreach ($id in @(101, 102)) {
        if (-not $strings.ContainsKey($id)) {
            throw "$ResourceSource does not define string resource $id."
        }
    }
    return $strings
}

function Assert-ResourceStrings([string]$Path, $ExpectedStrings) {
    foreach ($id in @(101, 102)) {
        $actual = [AxidevResourceStrings]::Read((Resolve-Path $Path).ProviderPath, $id)
        if ($actual -cne $ExpectedStrings[$id]) {
            throw "String resource $id in $Path does not match $ResourceSource."
        }
    }
}

$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$OutputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$TemporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) ("axidev-osk-resources-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $TemporaryDirectory | Out-Null

try {
    $ResourceObject = Join-Path $TemporaryDirectory "axidev-osk-resources.res"
    & $ResourceCompiler /nologo "/fo$ResourceObject" $ResourceSource
    if ($LASTEXITCODE -ne 0) {
        throw "The Windows resource compiler failed with exit code $LASTEXITCODE."
    }

    & $Link `
        /nologo `
        /dll `
        /noentry `
        /machine:x64 `
        /brepro `
        "/out:$OutputPath" `
        $ResourceObject
    if ($LASTEXITCODE -ne 0) {
        throw "The Microsoft linker failed with exit code $LASTEXITCODE."
    }

    $ExpectedStrings = Read-ExpectedStrings
    Assert-ResourceOnlyDll $OutputPath
    Assert-ResourceStrings $OutputPath $ExpectedStrings

    if ($VerifyAgainst) {
        Assert-ResourceOnlyDll $VerifyAgainst
        Assert-ResourceStrings $VerifyAgainst $ExpectedStrings
    }
} finally {
    Remove-Item -LiteralPath $TemporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Built resource-only DLL: $OutputPath"
if ($VerifyAgainst) {
    Write-Host "Verified resource strings against: $VerifyAgainst"
}
