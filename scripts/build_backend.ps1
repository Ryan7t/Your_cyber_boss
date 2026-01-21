$ErrorActionPreference = "Stop"

pyinstaller --onefile --name backend `
  --add-data "prompts;prompts" `
  server.py
