# Played inside a NEW console window by record_demo_video.py. Everything it shows is executed for real; only the typing is simulated (30 ms a key).
# Placeholders (@@...@@) are filled by the recorder. No key, token or personal path is used: the work folder is a short folder at the drive root.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'
$env:PATH = '@@VENV_SCRIPTS@@;' + $env:PATH
Set-Location '@@ROOT@@'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$null = cmd /c "chcp 65001 >nul"
$Host.UI.RawUI.WindowTitle = 'DelentiaDemoRec'
# A larger, readable font for THIS console window only (in-process call; no registry key and no setting of the user's is changed).
try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class ConFont {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct CFI { public uint cbSize; public uint nFont; public short X; public short Y; public int FontFamily; public int FontWeight;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string FaceName; }
    [DllImport("kernel32.dll", SetLastError = true)] public static extern IntPtr GetStdHandle(int h);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetCurrentConsoleFontEx(IntPtr h, bool max, ref CFI i);
    public static bool Set(short y) { var i = new CFI(); i.cbSize = (uint)Marshal.SizeOf(typeof(CFI)); i.FaceName = "Consolas"; i.FontFamily = 54; i.FontWeight = 400; i.X = 0; i.Y = y;
        return SetCurrentConsoleFontEx(GetStdHandle(-11), false, ref i); }
}
"@
    [void][ConFont]::Set(22)
} catch { }
cmd /c "mode con: cols=100 lines=28" | Out-Null
function Prompt { 'PS demo> ' }
Start-Transcript -Path '@@ROOT@@\transcript.txt' -Force | Out-Null
function Now { [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 }
function Shot($key) { Add-Content -Path '@@ROOT@@\events.txt' -Value ("{0:F3} {1}" -f (Now), $key) }
function TypeCmd($shown) {
    Write-Host -NoNewline 'PS demo> ' -ForegroundColor Green
    foreach ($ch in $shown.ToCharArray()) { Write-Host -NoNewline $ch; Start-Sleep -Milliseconds 30 }
    Write-Host ''
}
function Card($lines, $seconds) {
    Clear-Host
    Write-Host ''
    foreach ($l in $lines) { Write-Host ('  ' + $l[0]) -ForegroundColor $l[1] }
    Start-Sleep -Seconds $seconds
    Clear-Host
}
function ShowTail($text, $n) { ($text -split "`r?`n" | Where-Object { $_ -ne '' } | Select-Object -Last $n) | ForEach-Object { Write-Host $_ } }

New-Item -ItemType File -Force -Path '@@ROOT@@\ready.flag' | Out-Null
while (-not (Test-Path '@@ROOT@@\go.flag')) { Start-Sleep -Milliseconds 100 }
Shot 'go'

# ---- 0: title card
Shot 'title'
Card @(
    @('Delentia OS  @@VERSION@@', 'Cyan'),
    @('a governed agent runtime  -  EXPERIMENTAL', 'Yellow'),
    @('', 'Gray'),
    @('A risky action waits for a person''s signature.', 'White'),
    @('Every step goes into a hash-chained, signed log.', 'White'),
    @('', 'Gray'),
    @('No language model is used in this recording:', 'Gray'),
    @('a fixed script stands in for it. Tools, gate and log are real.', 'Gray')
) 7

# ---- 1: version
Shot 'version'
TypeCmd 'pip show delentia-os | Select-String Version'
pip show delentia-os | Select-String Version | ForEach-Object { Write-Host $_ }
Start-Sleep -Seconds 2
TypeCmd 'delentia demo init --lang en --dir demo'
$o = delentia demo init --lang en --dir demo 2>&1 | Out-String
ShowTail $o 3
Start-Sleep -Seconds 2

# ---- 2: compare
Clear-Host
Shot 'compare'
TypeCmd 'delentia demo run compare --scripted --dir demo | Select-Object -Last 16'
$o = delentia demo run compare --scripted --dir demo 2>&1 | Out-String
ShowTail $o 16
Start-Sleep -Seconds 5

# ---- 3: edit stops
Clear-Host
Shot 'edit_before'
TypeCmd 'Select-String "Total price" demo\workspace\quotes\vendor_a.md'
Select-String 'Total price' 'demo\workspace\quotes\vendor_a.md' | ForEach-Object { Write-Host $_.Line }
Start-Sleep -Seconds 2
Shot 'edit_waits'
TypeCmd 'delentia demo run edit --scripted --dir demo | Select-Object -Last 3'
$o = delentia demo run edit --scripted --dir demo 2>&1 | Out-String
ShowTail $o 3
$id = ([regex]::Match($o, 'approve ([0-9a-f]{12})')).Groups[1].Value
Start-Sleep -Seconds 2
TypeCmd 'Select-String "Total price" demo\workspace\quotes\vendor_a.md'
Select-String 'Total price' 'demo\workspace\quotes\vendor_a.md' | ForEach-Object { Write-Host $_.Line }
Start-Sleep -Seconds 5

# ---- 4: approve
Clear-Host
Shot 'approve'
TypeCmd ("delentia demo approve $id --scripted --dir demo | Select-Object -Last 6")
$o = delentia demo approve $id --scripted --dir demo 2>&1 | Out-String
ShowTail $o 6
Start-Sleep -Seconds 2
TypeCmd 'Select-String "Total price" demo\workspace\quotes\vendor_a.md'
Select-String 'Total price' 'demo\workspace\quotes\vendor_a.md' | ForEach-Object { Write-Host $_.Line }
Start-Sleep -Seconds 5

# ---- 5: tamper evidence on a copy
Clear-Host
Shot 'chain_ok'
TypeCmd 'delentia demo status --dir demo | Select-Object -First 9'
$o = delentia demo status --dir demo 2>&1 | Out-String
ShowTail $o 9 | Out-Null
($o -split "`r?`n" | Select-Object -First 9) | ForEach-Object { Write-Host $_ }
Start-Sleep -Seconds 3
Shot 'tamper'
TypeCmd 'Copy-Item demo demo_copy -Recurse     # a throw-away copy'
Copy-Item demo demo_copy -Recurse
TypeCmd 'python alter_one_character.py demo_copy\data\agentic.db 3'
python alter_one_character.py demo_copy\data\agentic.db 3 2>&1 | ForEach-Object { Write-Host $_ }
Start-Sleep -Seconds 2
TypeCmd 'delentia demo status --dir demo_copy | Select-Object -First 9'
$o = delentia demo status --dir demo_copy 2>&1 | Out-String
($o -split "`r?`n" | Select-Object -First 9) | ForEach-Object { Write-Host $_ }
Start-Sleep -Seconds 6

# ---- 6: measured / not yet
Shot 'card_measured'
Card @(
    @('MEASURED', 'Green'),
    @('  - @@TESTS_LINE@@', 'White'),
    @('  - A scripted, hijacked model: 0 of 23 side effects ran with the taint rule on', 'White'),
    @('  - The cost meter agreed with the provider''s own figure (within 10%)', 'White'),
    @('', 'Gray'),
    @('NOT YET', 'Red'),
    @('  - Results with a strong model on long tasks', 'White'),
    @('  - Any outside user; an independent witness for the log', 'White'),
    @('  - RCT-7 and FDIA D^I have no measured benefit yet', 'White'),
    @('  - The Windows installer is not code-signed', 'White')
) 10

# ---- 7: try it
Shot 'try_it'
Card @(
    @('Run it yourself - no model, no API key:', 'Cyan'),
    @('', 'Gray'),
    @('  pip install delentia-os', 'White'),
    @('  delentia demo init --lang en', 'White'),
    @('  delentia demo run compare --scripted', 'White'),
    @('  delentia demo run edit --scripted', 'White'),
    @('', 'Gray'),
    @('  github.com/delentia-labs/Delentia-OS', 'Yellow'),
    @('  Technical preview. Tell me where it breaks.', 'Gray')
) 8
Shot 'end'
Stop-Transcript | Out-Null
New-Item -ItemType File -Force -Path '@@ROOT@@\done.flag' | Out-Null
