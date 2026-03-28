# Vite Project Manager

<<<<<<< Updated upstream
Desktop app for creating and managing local Vite and Electron projects from one place.

> [!IMPORTANT]
> You are required to install `nvm` and a Node.js version before using this app. Project creation depends on `npm`, and this app looks for Node.js through your active `nvm` setup.
=======
Desktop app for creating and managing local Vite, Electron, Node module, Chrome extension, and native starter projects from one place.

> [!IMPORTANT]
> You need `nvm` and an active Node.js version for the Vite, Electron, Node module, and Chrome extension generators. The native `C`, `C++`, and `C#` starters are scaffolded locally.
>>>>>>> Stashed changes

## What It Does

- Creates new Vite projects inside the `projects/` folder
- Creates new Electron apps inside the `projects/` folder
<<<<<<< Updated upstream
- Opens a setup shell that runs `npm install` after project creation
=======
- Creates new Node module projects with `JavaScript` or `TypeScript` starter templates
- Creates new Chrome extension projects with `JavaScript` or `TypeScript` starter templates
- Creates new `C`, `C++`, and `C#` starter apps from the `Nonsense category`
- Clones Chromium from GitHub (with tag fetch) from the `Nonsense category`
- Opens a repo cloning window that fetches GitHub tags and clones a repo at an exact tag
- Lets you choose `npm` or `yarn` when creating a project
- Opens a setup shell that runs `npm install` or `yarn install` after project creation
>>>>>>> Stashed changes
- Opens project folders in VS Code
- Opens a shell in any managed project folder
- Deletes projects, including handling locked files when possible

## Requirements

- Windows
- Python 3.11+
- `nvm` for Windows
- A Node.js version installed through `nvm`
<<<<<<< Updated upstream
=======
- `yarn` installed if you want to use the Yarn option
>>>>>>> Stashed changes
- VS Code on your `PATH` if you want the editor launch button to work

## Setup

1. Install Python.
2. Install `nvm` for Windows.
3. Install and activate a Node.js version:

```powershell
nvm install 20
nvm use 20
```
<<<<<<< Updated upstream
once done execute those following commands
```powershell
pip install -r requirements.txt
```
and then
```powershell
python ./main.py
```
and then ready
=======

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
- `projects/` - generated Vite, Electron, Node module, Chrome extension, and native starter projects
- `requirements.txt` - Python dependencies

## Notes

- If your selected package manager cannot be found, project creation will fail until Node.js is installed and active through `nvm`.
- New projects are created directly inside `projects/<name>`.
- Chrome extension templates are loaded as unpacked extensions from `dist/` after running the generated build script.
- Native starter apps are scaffolded locally and open a regular command prompt instead of a package-manager setup shell.
>>>>>>> Stashed changes
