# Android 9 最后可用世代的 WebView（135/130）：APKMirror dance 下载 base apk
# 用法：右键“使用 PowerShell 运行”（与今天 getwv.ps1 同套路，自动重试）
$A="https://www.apkmirror.com"
$UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
$dir="C:\work\phonebox\webview"
$jar="C:\work\phonebox\webview\cookies.txt"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Remove-Item $jar -ErrorAction SilentlyContinue

$targets = @(
  @{name="webview135.apk"; slugs=@("android-system-webview-135-0-7049-111-release","android-system-webview-135-0-7049-126-release","android-system-webview-135-0-7049-91-release","android-system-webview-135-0-7049-75-release","android-system-webview-135-0-7049-49-release")},
  @{name="webview130.apk"; slugs=@("android-system-webview-130-0-6723-103-release","android-system-webview-130-0-6723-86-release","android-system-webview-130-0-6723-58-release")}
)

foreach ($t in $targets) {
  $out = "$dir\" + $t.name
  if (Test-Path $out) { "SKIP $($t.name) exists"; continue }
  $got = $false
  foreach ($slug in $t.slugs) {
    if ($got) { break }
    for ($i=0; $i -lt 3; $i++) {
      $l = "$A/apk/google-inc/android-system-webview/$slug/"
      $s1 = curl.exe -s -c $jar -b $jar -A $UA -H "Accept-Language: en-US,en;q=0.9" --max-time 30 -w "%{http_code}" "$l" -o "$dir\v1.html"
      $k  = [regex]::Match((Get-Content "$dir\v1.html" -Raw -EA SilentlyContinue),'download/\?key=([0-9a-f]+)').Groups[1].Value
      "[$($t.name) $slug] page=$s1 keylen=$($k.Length)"
      if (-not $k) { Start-Sleep -Seconds 20; continue }
      $s2 = curl.exe -s -c $jar -b $jar -A $UA -H "Referer: $l" -H "Accept-Language: en-US,en;q=0.9" --max-time 30 -w "%{http_code}" "$l/download/?key=$k&forcebaseapk=true" -o "$dir\v2.html"
      $dl = [regex]::Match((Get-Content "$dir\v2.html" -Raw -EA SilentlyContinue),'download\.php\?id=[0-9]+&key=[0-9a-f]+').Value
      "[$($t.name)] form=$s2 dl=$([bool]$dl)"
      if (-not $dl) { Start-Sleep -Seconds 20; continue }
      $code = curl.exe -s -c $jar -b $jar -A $UA -H "Referer: $l" --max-time 300 -L -o $out -w "%{http_code} %{size_download}" "$A/wp-content/themes/APKMirror/$dl"
      "[$($t.name)] fetch=$code"
      $sz = (Get-Item $out -EA SilentlyContinue).Length
      if ($sz -gt 20MB) { $got = $true; "OK $($t.name) $([math]::Round($sz/1MB))MB" } else { Remove-Item $out -EA SilentlyContinue; Start-Sleep -Seconds 20 }
      break
    }
  }
  if (-not $got) { "FAIL $($t.name)" }
}
"DONE - files in $dir"
