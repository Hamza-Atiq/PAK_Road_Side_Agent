# One-time setup script for the Flutter mobile app.
# Run from apps/mobile/ in PowerShell after `flutter create .` succeeds.
#
# What it does:
#   1. Patches AndroidManifest.xml with INTERNET, LOCATION, CAMERA, CALL_PHONE perms
#   2. Adds tel: queries intent so url_launcher can dial
#
# Idempotent — safe to re-run.

$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PSScriptRoot 'android\app\src\main\AndroidManifest.xml'

if (-not (Test-Path $manifestPath)) {
    Write-Host "ERROR: $manifestPath not found." -ForegroundColor Red
    Write-Host "Run 'flutter create . --org com.roadsideagent --project-name roadside_mobile --platforms=android,ios' first." -ForegroundColor Yellow
    exit 1
}

$xml = Get-Content -Path $manifestPath -Raw

$permissions = @"
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
    <uses-permission android:name="android.permission.CALL_PHONE" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />
    <uses-feature android:name="android.hardware.location.gps" android:required="false" />
"@

$queries = @"
    <queries>
        <intent>
            <action android:name="android.intent.action.DIAL" />
            <data android:scheme="tel" />
        </intent>
    </queries>
"@

if ($xml -notmatch 'ACCESS_FINE_LOCATION') {
    $xml = $xml -replace '(<application)', "$permissions`r`n`$1"
    Write-Host '✓ Added Android permissions' -ForegroundColor Green
} else {
    Write-Host '• Permissions already present, skipping' -ForegroundColor Yellow
}

if ($xml -notmatch '<queries>') {
    $xml = $xml -replace '(</application>)', "`$1`r`n$queries"
    Write-Host '✓ Added tel: queries intent' -ForegroundColor Green
} else {
    Write-Host '• Queries already present, skipping' -ForegroundColor Yellow
}

Set-Content -Path $manifestPath -Value $xml -Encoding UTF8
Write-Host ''
Write-Host 'AndroidManifest.xml patched successfully.' -ForegroundColor Green
Write-Host 'Next: flutter pub get && flutter run' -ForegroundColor Cyan
