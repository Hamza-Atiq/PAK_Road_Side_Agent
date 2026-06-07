# One-time setup script for the Flutter mobile app.
# Run from apps/mobile/ in PowerShell after `flutter create .` succeeds.
#
# What it does:
#   1. Ensures assets/images/ exists (referenced in pubspec.yaml)
#   2. Patches AndroidManifest.xml with INTERNET, LOCATION, CAMERA, CALL_PHONE perms
#      + tel: queries intent so url_launcher can dial
#   3. Aligns Java + Kotlin JVM target to 17 in android/app/build.gradle(.kts)
#
# Idempotent — safe to re-run.

$ErrorActionPreference = 'Stop'

# ---- 1. Assets folder ----
$assetsDir = Join-Path $PSScriptRoot 'assets\images'
if (-not (Test-Path $assetsDir)) {
    New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $assetsDir '.gitkeep') -Force | Out-Null
    Write-Host "OK  Created assets/images/" -ForegroundColor Green
} else {
    Write-Host "..  assets/images/ already exists" -ForegroundColor Yellow
}

# ---- 2. AndroidManifest.xml permissions ----
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
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
    <uses-permission android:name="android.permission.CALL_PHONE" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />
    <uses-feature android:name="android.hardware.location.gps" android:required="false" />
    <uses-feature android:name="android.hardware.microphone" android:required="false" />
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
    Write-Host "OK  Added Android permissions" -ForegroundColor Green
} else {
    Write-Host "..  Permissions already present" -ForegroundColor Yellow
}

if ($xml -notmatch 'android.intent.action.DIAL') {
    $xml = $xml -replace '(</application>)', "`$1`r`n$queries"
    Write-Host "OK  Added tel: queries intent" -ForegroundColor Green
} else {
    Write-Host "..  Queries already present" -ForegroundColor Yellow
}

Set-Content -Path $manifestPath -Value $xml -Encoding UTF8

# ---- 3. JVM target alignment (Java 17 + Kotlin 17) ----
$gradleKts = Join-Path $PSScriptRoot 'android\app\build.gradle.kts'
$gradleGroovy = Join-Path $PSScriptRoot 'android\app\build.gradle'

if (Test-Path $gradleKts) {
    $g = Get-Content -Path $gradleKts -Raw
    $original = $g

    # Replace VERSION_11 / VERSION_1_8 / VERSION_1_11 with VERSION_17
    $g = [System.Text.RegularExpressions.Regex]::Replace($g, 'JavaVersion\.VERSION_(?:1_8|11|1_11)', 'JavaVersion.VERSION_17')
    # Force kotlinOptions jvmTarget
    $g = [System.Text.RegularExpressions.Regex]::Replace($g, 'jvmTarget\s*=\s*"[^"]+"', 'jvmTarget = "17"')
    # Force compileOptions if it's still set via JavaVersion.toString()
    $g = [System.Text.RegularExpressions.Regex]::Replace($g, 'jvmTarget\s*=\s*JavaVersion\.\w+\.toString\(\)', 'jvmTarget = "17"')

    if ($g -ne $original) {
        Set-Content -Path $gradleKts -Value $g -Encoding UTF8
        Write-Host "OK  Pinned Java + Kotlin to JVM 17 in build.gradle.kts" -ForegroundColor Green
    } else {
        Write-Host "..  JVM target already 17 (or pattern not matched - inspect build.gradle.kts manually)" -ForegroundColor Yellow
    }
} elseif (Test-Path $gradleGroovy) {
    $g = Get-Content -Path $gradleGroovy -Raw
    $original = $g
    $g = [System.Text.RegularExpressions.Regex]::Replace($g, 'JavaVersion\.VERSION_(?:1_8|11|1_11)', 'JavaVersion.VERSION_17')
    $g = [System.Text.RegularExpressions.Regex]::Replace($g, "jvmTarget\s*=\s*['""][^'""]+['""]", 'jvmTarget = "17"')
    if ($g -ne $original) {
        Set-Content -Path $gradleGroovy -Value $g -Encoding UTF8
        Write-Host "OK  Pinned Java + Kotlin to JVM 17 in build.gradle" -ForegroundColor Green
    } else {
        Write-Host "..  JVM target already 17 (or pattern not matched - inspect build.gradle manually)" -ForegroundColor Yellow
    }
} else {
    Write-Host "WARN: No android/app/build.gradle(.kts) found." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: flutter run" -ForegroundColor Cyan
