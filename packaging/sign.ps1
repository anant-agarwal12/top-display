# Authenticode-signs the files it is given, using a certificate named in the environment.
# Does nothing (and succeeds) when no certificate is configured, so an unsigned build still works.
#
#   TD_SIGN_PFX             path to a .pfx file          -- or --
#   TD_SIGN_THUMBPRINT      thumbprint of a certificate in CurrentUser\My / LocalMachine\My
#                           (use this for hardware tokens and cloud HSMs that expose the key
#                           through the Windows certificate store)
#   TD_SIGN_PFX_PASSWORD    password for the .pfx
#   TD_SIGN_TIMESTAMP_URL   RFC 3161 timestamp server (default: http://timestamp.digicert.com)
#
# The timestamp is not optional: without it the signature stops being valid the day the
# certificate expires. Signing fails (non-zero exit) if the timestamp server cannot be reached.
#
#   powershell -ExecutionPolicy Bypass -File packaging\sign.ps1 <file> [<file> ...]
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Path)
$ErrorActionPreference = 'Stop'

if (-not $env:TD_SIGN_PFX -and -not $env:TD_SIGN_THUMBPRINT) {
    Write-Host "sign.ps1: no certificate configured (TD_SIGN_PFX / TD_SIGN_THUMBPRINT) -- leaving unsigned: $($Path -join ', ')"
    exit 0
}

if ($env:TD_SIGN_PFX) {
    if (-not (Test-Path -LiteralPath $env:TD_SIGN_PFX)) { throw "TD_SIGN_PFX not found: $env:TD_SIGN_PFX" }
    $password = if ($env:TD_SIGN_PFX_PASSWORD) { $env:TD_SIGN_PFX_PASSWORD } else { '' }
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($env:TD_SIGN_PFX, $password)
} else {
    $thumb = ($env:TD_SIGN_THUMBPRINT -replace '\s', '').ToUpperInvariant()
    $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
    if (-not $cert) { throw "No certificate with thumbprint $thumb in CurrentUser\My or LocalMachine\My" }
}
if (-not $cert.HasPrivateKey) { throw "The signing certificate has no private key available" }

$timestamp = if ($env:TD_SIGN_TIMESTAMP_URL) { $env:TD_SIGN_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }

foreach ($file in $Path) {
    $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $timestamp
    # "Valid" with a trusted certificate. A certificate Windows does not trust (for example a
    # self-signed test one) still signs correctly but reports UnknownError; anything else is a failure.
    if ($result.Status -notin @('Valid', 'UnknownError') -or -not $result.SignerCertificate) {
        throw "Signing $file failed: $($result.Status) $($result.StatusMessage)"
    }
    if (-not $result.TimeStamperCertificate) { throw "Signing $file produced no timestamp" }
    Write-Host "sign.ps1: signed $file as '$($cert.Subject)' ($($result.Status))"
}
