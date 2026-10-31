# Runs a sample here against this checkout's build:
#     run.ps1 [-Validate] [-Script compute.py] [args...]
# (shadows.py by default).  Output goes to the console; with -Validate the
# Khronos layer (with its synchronization checks) is on and its messages are
# counted at the end.
[CmdletBinding(PositionalBinding = $false)]
param([switch]$Validate, [string]$Script = "shadows.py", [Parameter(ValueFromRemainingArguments)]$Rest)
$root = Resolve-Path "$PSScriptRoot\..\.."
$env:PYTHONPATH = "$root\built"
$env:PATH = "$root\built\bin;$env:PATH"
$prc = "sync-video 0"
if ($Validate) {
    $env:VK_LAYER_PATH = 'C:\VulkanSDK\1.4.363.0\Bin'
    $env:VK_KHRONOS_VALIDATION_VALIDATE_SYNC = 'true'
    $prc += "`nvulkan-validation true"
}
$code = "import faulthandler, runpy, sys; faulthandler.enable(); faulthandler.dump_traceback_later(400, exit=True); " +
        "from panda3d.core import loadPrcFileData; loadPrcFileData('', sys.argv[1].replace('|', chr(10))); " +
        "sys.argv = ['$Script'] + sys.argv[2:]; runpy.run_path(r'$PSScriptRoot\$Script', run_name='__main__')"
$log = "$PSScriptRoot\run.log"
& "$root\venv\Scripts\python.exe" -c $code ($prc -replace "`n", "|") @Rest 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log | Out-Null
$status = $LASTEXITCODE
Get-Content $log | Where-Object { $_ -notmatch '^\s*(At line|\+ |CategoryInfo|FullyQualifiedErrorId)' } | Select-Object -First 80
if ($Validate) {
    $errors = (Select-String -Path $log -Pattern 'Validation Error|VUID-|SYNC-HAZARD' | Measure-Object).Count
    "validation messages: $errors"
}
"exit $status"
