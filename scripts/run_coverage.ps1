# Quick test runner with coverage for PowerShell

param(
    [string[]]$TestPath = ""
)

Write-Host "🚀 Running tests with coverage..." -ForegroundColor Green
Write-Host ""

# Build pytest command
$pytestArgs = @(
    "--cov=packages/",
    "--cov-report=html:htmlcov",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=xml:coverage.xml",
    "--cov-branch",
    "--cov-fail-under=0",
    "-v"
)

if ($TestPath) {
    $pytestArgs += $TestPath
}

# Run tests
$process = Start-Process -FilePath "pixi" -ArgumentList "run","python","-m","pytest" + $pytestArgs -Wait -PassThru -NoNewWindow

if ($process.ExitCode -eq 0) {
    Write-Host ""
    Write-Host "✅ Tests passed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Coverage reports generated:" -ForegroundColor Cyan
    Write-Host "   - HTML: htmlcov/index.html"
    Write-Host "   - XML: coverage.xml"
    Write-Host ""
    Write-Host "💡 Run 'python scripts/view_coverage.py --open' to view HTML report" -ForegroundColor Yellow
    Write-Host "💡 Run 'python scripts/view_coverage.py --summary' for quick summary" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "❌ Some tests failed" -ForegroundColor Red
    exit $process.ExitCode
}
