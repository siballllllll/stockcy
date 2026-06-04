Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")

' 1. Launch FastAPI Backend silently (Port 8000)
WshShell.Run "cmd.exe /c cd /d """ & ScriptDir & """ && .\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload", 0, False

' 2. Launch Next.js Frontend silently (Port 3000)
WshShell.Run "cmd.exe /c set PATH=%PATH%;C:\Program Files\nodejs\ && cd /d """ & ScriptDir & "\frontend"" && call npm run dev", 0, False

' 3. Launch Unified Proxy Gateway silently (Port 3500)
WshShell.Run "cmd.exe /c set PATH=%PATH%;C:\Program Files\nodejs\ && cd /d """ & ScriptDir & """ && node scratch\dev_proxy.js", 0, False

' 4. Launch Cloudflare Tunnel silently (Port 3500 to stockcy.trade)
WshShell.Run "cmd.exe /c cd /d """ & ScriptDir & """ && .\venv\Scripts\python.exe scratch\run_cloudflared.py", 0, False
