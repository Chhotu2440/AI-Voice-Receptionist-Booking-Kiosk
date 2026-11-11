# Windows 11 kiosk: keeps Chrome open full-screen on the kiosk page and restarts it if it crashes or is closed
# (KIOSK-06 "browser watchdog"). Run at logon of the kiosk user via Task Scheduler:
#   Trigger: At log on (kiosk user) - Action: powershell.exe -ExecutionPolicy Bypass -File C:\kiosk\start-kiosk.ps1
# Set $KioskUrl to the kiosk address (HTTPS is required for the service worker and the camera/mic).
$KioskUrl = "https://kiosk.example.com/"
$Chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$ChromeArgs = @("--kiosk", "--noerrdialogs", "--disable-session-crashed-bubble", "--disable-infobars",
                "--autoplay-policy=no-user-gesture-required", $KioskUrl)
while ($true) {
    $p = Start-Process -FilePath $Chrome -ArgumentList $ChromeArgs -PassThru
    $p.WaitForExit()
    Start-Sleep -Seconds 3
}
