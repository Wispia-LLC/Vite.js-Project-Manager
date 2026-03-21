# Vite Project Manager

Desktop app for creating and managing local Vite and Electron projects from one place.

> [!IMPORTANT]
> You are required to install `nvm` and a Node.js version before using this app. Project creation depends on `npm`, and this app looks for Node.js through your active `nvm` setup.

## What It Does

- Creates new Vite projects inside the `projects/` folder
- Creates new Electron apps inside the `projects/` folder
- Opens a setup shell that runs `npm install` after project creation
- Opens project folders in VS Code
- Opens a shell in any managed project folder
- Deletes projects, including handling locked files when possible

## Requirements

- Windows
- Python 3.11+
- `nvm` for Windows
- A Node.js version installed through `nvm`
- VS Code on your `PATH` if you want the editor launch button to work

## Setup

1. Install Python.
2. Install `nvm` for Windows.
3. Install and activate a Node.js version:

```powershell
nvm install 20
nvm use 20
```

4. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Project Structure

- `main.py` - app entry point and UI logic
- `projects/` - generated Vite and Electron projects
- `requirements.txt` - Python dependencies

## Notes

- If `npm` cannot be found, project creation will fail until Node.js is installed and active through `nvm`.
- New projects are created directly inside `projects/<name>`.
