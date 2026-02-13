$paths = @(
    "C:\Program Files\Windows Media Player\wmplayer.exe",
    "C:\Program Files (x86)\Windows Media Player\wmplayer.exe"
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        $s = Get-AuthenticodeSignature $p
        Write-Output "Path: $p"
        Write-Output "  Status: $($s.Status)"
        Write-Output "  IsOSBinary: $($s.IsOSBinary)"
        Write-Output "  Signer: $($s.SignerCertificate.Subject)"
        Write-Output ""
    }
}
