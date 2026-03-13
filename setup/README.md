# Setup Details

This folder contains the setup scripts. Run from the **repo root**:

| Platform | Command |
|----------|---------|
| macOS / Linux | `bash setup/setup.sh` |
| Windows (PowerShell) | `.\setup\setup.ps1` |

The scripts handle everything automatically: Python check, virtual environment, dependency install, and config scaffolding.

---

## What the script does

1. Verifies Python 3.10+ is installed
2. Creates `.venv/` (virtual environment) — isolated Python for this project only
3. Installs `jobfinder` and all dependencies into `.venv/`
4. Creates `config.json` from the example (skipped if already exists)
5. Creates `.env` from the example (skipped if already exists)
6. Prints next steps

**Why a virtual environment?** It keeps this project's packages separate from your system Python so nothing conflicts with other tools you have installed. You don't need to understand it — the script handles it.

---

## Adding your API key

Open `.env` in any text editor and replace the placeholder:

```
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

Get a key:
- **Anthropic (Claude):** https://console.anthropic.com
- **Google Gemini (free tier):** https://aistudio.google.com

You only need one. The `model_provider` field in `config.json` controls which one is used.

To avoid pasting the key every session, add it to your shell profile:

```bash
# macOS/Linux — add to ~/.zshrc or ~/.bashrc
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc

# Windows — set a persistent user environment variable
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

---

## Starting the app

After setup, you need to activate the virtual environment **once per terminal session**:

```bash
# macOS / Linux
source .venv/bin/activate
jobfinder serve

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
jobfinder serve
```

Then open **http://localhost:8000**.

You'll know the venv is active when you see `(.venv)` at the start of your terminal prompt.

---

## Troubleshooting

**`python3: command not found`**
Install Python from https://python.org (3.10 or newer). On macOS, Homebrew works too: `brew install python@3.12`.

**`bash: setup/setup.sh: Permission denied`**
Run `chmod +x setup/setup.sh` then try again.

**Windows: "running scripts is disabled"**
Open PowerShell as Administrator and run:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`jobfinder: command not found` after setup**
You need to activate the venv first: `source .venv/bin/activate` (macOS/Linux) or `.\.venv\Scripts\Activate.ps1` (Windows).

**Port 8000 already in use**
Run `jobfinder serve --port 8001` and open http://localhost:8001.

---

## UI development (optional)

Only needed if you want to modify the frontend. Requires Node 20+.

```bash
# Install Node 20 via nvm (macOS/Linux)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
nvm install 20 && nvm use 20

# Install pnpm
npm install -g pnpm

# Terminal 1 — Python API
source .venv/bin/activate
jobfinder serve --reload

# Terminal 2 — Vite dev server (hot reload at :5173)
cd ui
pnpm install
pnpm dev
```

Build and bundle the frontend (output goes to `ui/dist/`, served automatically by `jobfinder serve`):

```bash
cd ui && pnpm build
```

---

## Browser agent (optional)

For companies that require JavaScript rendering or interactive pagination:

```bash
source .venv/bin/activate
pip install "jobfinder[browser-use,langchain-anthropic]"   # or langchain-google-genai
playwright install chromium
```

After this, flagged companies in the UI will show a **Fetch via Browser Agent** button.
