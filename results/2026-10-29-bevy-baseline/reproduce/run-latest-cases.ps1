$env:TIDE_HIDDEN = '1'
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$cases = @('particles-1m-1','particles-1m-4','wide-1m-1','wide-1m-4','filtered-1m-1','filtered-1m-4','filtered-frozen95-1m-1','filtered-frozen99-1m-1','filtered-frozen99-1m-4','churn-2k-1','churn-2k-4')
$base = 'build/bevy-latest-fe5e96be1-cases'
New-Item -ItemType Directory -Path $base | Out-Null
$accepted = @()
foreach ($case in $cases) {
    $valid = $false
    foreach ($attempt in 1..3) {
        $dest = "$base/$case-attempt$attempt"
        try {
            & ./bench/bevy/run.ps1 -OutputDir $dest -Rounds 3 -FilterSweep -OnlyCases $case -BuildDir build/bevy-latest-moving -BevyExe build/bevy-table/release/tide-bevy-bench.exe *> "$base/$case-attempt$attempt.log"
            python bench/bevy/analyze.py $dest > "$base/$case-attempt$attempt-analysis.log" 2>&1
            if ($LASTEXITCODE) { throw 'Analysis failed' }
            $accepted += $dest
            $valid = $true
            Write-Output "ACCEPTED $case attempt $attempt"
            break
        } catch {
            Write-Output "REJECTED $case attempt $attempt : $_"
            if (!(Test-Path -LiteralPath "$dest/metadata.json")) { throw }
            $meta = Get-Content -LiteralPath "$dest/metadata.json" -Raw | ConvertFrom-Json
            if ($meta.complete) { throw }
            $rows = @(Get-Content -LiteralPath "$dest/records.jsonl" -ErrorAction SilentlyContinue | ForEach-Object { $_ | ConvertFrom-Json })
            if (!($rows | Where-Object { $_.contended })) { throw }
        }
    }
    if (!$valid) { throw "No uncontended complete result for $case after three attempts" }
    $accepted | ConvertTo-Json -AsArray | Set-Content -LiteralPath "$base/accepted.json" -Encoding utf8
}
