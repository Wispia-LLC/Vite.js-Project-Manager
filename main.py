from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib import error, request

import customtkinter as ctk
import psutil
from tkinter import messagebox, simpledialog


ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT_DIR / "projects"
PACKAGE_MANAGERS = ("npm", "yarn")
NODE_TEMPLATES = ("JavaScript", "TypeScript")
NATIVE_TEMPLATES = ("C", "C++", "C#")
CHROMIUM_REPO_SLUG = "chromium/chromium"
CHROMIUM_REPO_URL = f"https://github.com/{CHROMIUM_REPO_SLUG}.git"


def ensure_projects_dir() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_github_tags(repo_slug: str, limit: int | None = None) -> list[str]:
    try:
        slug = normalize_repo_slug(repo_slug)
    except ValueError:
        return []

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "vite-proj-manager",
    }

    tags: list[str] = []
    page = 1
    per_page = 100

    while True:
        remaining = None if limit is None else limit - len(tags)
        if remaining is not None and remaining <= 0:
            break

        page_size = per_page if remaining is None else min(per_page, remaining)
        url = f"https://api.github.com/repos/{slug}/tags?per_page={page_size}&page={page}"
        request_obj = request.Request(url, headers=headers)

        try:
            with request.urlopen(request_obj, timeout=15) as response:
                data = json.load(response)
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            break

        if not isinstance(data, list) or not data:
            break

        for item in data:
            name = item.get("name")
            if isinstance(name, str) and name:
                tags.append(name)

        page += 1

    return tags


def build_node_tool_env() -> dict[str, str]:
    env = os.environ.copy()
    path_parts = env.get("PATH", "").split(os.pathsep)

    extra_paths: list[str] = []

    for key in ("NVM_SYMLINK", "NVM_HOME"):
        value = env.get(key)
        if value:
            extra_paths.append(value)

    local_nvm_home = Path.home() / "AppData" / "Local" / "nvm"
    local_nvm_symlink = Path("C:/nvm4w/nodejs")

    if local_nvm_home.exists():
        extra_paths.append(str(local_nvm_home))
    if local_nvm_symlink.exists():
        extra_paths.append(str(local_nvm_symlink))

    seen: set[str] = set()
    merged_path: list[str] = []
    for entry in extra_paths + path_parts:
        if not entry:
            continue
        normalized = os.path.normcase(os.path.normpath(entry))
        if normalized in seen:
            continue
        seen.add(normalized)
        merged_path.append(entry)

    env["PATH"] = os.pathsep.join(merged_path)
    return env


def resolve_package_manager_command(package_manager: str) -> tuple[list[str], dict[str, str]]:
    if package_manager not in PACKAGE_MANAGERS:
        raise ValueError(f"Unsupported package manager: {package_manager}")

    env = build_node_tool_env()

    for candidate in (f"{package_manager}.cmd", package_manager):
        resolved = shutil.which(candidate, path=env.get("PATH"))
        if resolved:
            return [resolved], env

    raise FileNotFoundError(f"{package_manager} was not found on PATH.")


def sanitize_name(name: str) -> str:
    cleaned = name.strip()
    invalid = '<>:"/\\|?*'
    if not cleaned:
        raise ValueError("Project name cannot be empty.")
    if any(char in invalid for char in cleaned):
        raise ValueError(f"Project name cannot contain any of: {invalid}")
    return cleaned


def normalize_repo_slug(raw_slug: str) -> str:
    slug = raw_slug.strip().removesuffix(".git").replace("\\", "/")
    if slug.count("/") != 1:
        raise ValueError("Enter repo as owner/name.")

    owner, name = slug.split("/", 1)
    pattern = r"^[A-Za-z0-9_.-]+$"
    if not owner or not name or not re.match(pattern, owner) or not re.match(pattern, name):
        raise ValueError("Repo can only use letters, numbers, ., _, and -.")

    return f"{owner}/{name}"


def to_package_name(project_name: str) -> str:
    package_name = "".join(
        char.lower() if char.isalnum() else "-"
        for char in project_name.strip()
    )
    while "--" in package_name:
        package_name = package_name.replace("--", "-")
    package_name = package_name.strip("-._")
    if not package_name:
        raise ValueError("Project name cannot be converted to a valid package name.")
    return package_name


def write_text_file(file_path: Path, content: str) -> None:
    file_path.write_text(content, encoding="utf-8")


def scaffold_node_module_project(project_dir: Path, project_name: str, template: str, package_manager: str) -> None:
    package_name = to_package_name(project_name)
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    if template == "TypeScript":
        package_json = f"""{{
  \"name\": \"{package_name}\",
  \"version\": \"1.0.0\",
  \"private\": true,
  \"type\": \"module\",
  \"main\": \"dist/index.js\",
  \"types\": \"dist/index.d.ts\",
  \"scripts\": {{
    \"build\": \"tsc\",
    \"dev\": \"tsx src/index.ts\",
    \"start\": \"node dist/index.js\"
  }},
  \"devDependencies\": {{
    \"@types/node\": \"^24.0.0\",
    \"tsx\": \"^4.19.0\",
    \"typescript\": \"^5.8.0\"
  }},
  \"packageManager\": \"{package_manager}\"
}}
"""
        tsconfig_json = """{
  \"compilerOptions\": {
    \"target\": \"ES2022\",
    \"module\": \"NodeNext\",
    \"moduleResolution\": \"NodeNext\",
    \"declaration\": true,
    \"outDir\": \"dist\",
    \"rootDir\": \"src\",
    \"strict\": true,
    \"esModuleInterop\": true,
    \"skipLibCheck\": true
  },
  \"include\": [\"src/**/*.ts\"]
}
"""
        entry_file = src_dir / "index.ts"
        entry_content = """export function greet(name: string): string {
  return `Hello, ${name}!`
}

if (import.meta.url === `file://${process.argv[1]?.replace(/\\/g, \"/\")}`) {
  console.log(greet(\"world\"))
}
"""
        write_text_file(project_dir / "tsconfig.json", tsconfig_json)
    else:
        package_json = f"""{{
  \"name\": \"{package_name}\",
  \"version\": \"1.0.0\",
  \"private\": true,
  \"type\": \"module\",
  \"main\": \"src/index.js\",
  \"scripts\": {{
    \"start\": \"node src/index.js\"
  }},
  \"packageManager\": \"{package_manager}\"
}}
"""
        entry_file = src_dir / "index.js"
        entry_content = """export function greet(name) {
  return `Hello, ${name}!`
}

console.log(greet("world"))
"""

    readme_content = f"# {project_name}\n\nGenerated by Vite Project Manager as a Node module ({template}).\n"
    gitignore_content = "node_modules/\ndist/\n"

    write_text_file(project_dir / "package.json", package_json)
    write_text_file(project_dir / "README.md", readme_content)
    write_text_file(project_dir / ".gitignore", gitignore_content)
    write_text_file(entry_file, entry_content)


def scaffold_chrome_extension_project(project_dir: Path, project_name: str, template: str, package_manager: str) -> None:
    package_name = to_package_name(project_name)
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    popup_html_content = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>{project_name}</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: "Segoe UI", sans-serif;
      }}

      body {{
        margin: 0;
        min-width: 320px;
        min-height: 220px;
        background: linear-gradient(160deg, #f2f7ff 0%, #e0f2fe 100%);
        color: #0f172a;
      }}

      main {{
        padding: 20px;
      }}

      h1 {{
        margin: 0 0 8px;
        font-size: 1.2rem;
      }}

      p {{
        margin: 0 0 10px;
        line-height: 1.5;
      }}

      .status {{
        margin-top: 14px;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.8);
        font-size: 0.95rem;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>{project_name}</h1>
      <p>Edit the popup and manifest files in <code>src/</code> to start building your extension.</p>
      <div class=\"status\" data-role=\"status\">Loading extension status...</div>
    </main>
    <script type=\"module\" src=\"./popup.js\"></script>
  </body>
</html>
"""
    manifest_content = f"""{{
  "manifest_version": 3,
  "name": "{project_name}",
  "version": "1.0.0",
  "description": "A Chrome extension generated by Vite Project Manager.",
  "action": {{
    "default_title": "{project_name}",
    "default_popup": "popup.html"
  }},
  "background": {{
    "service_worker": "background.js",
    "type": "module"
  }},
  "permissions": ["storage"]
}}
"""

    if template == "TypeScript":
        package_json = f"""{{
  "name": "{package_name}",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {{
    "build": "node scripts/build-extension.mjs",
    "dev": "node scripts/build-extension.mjs"
  }},
  "devDependencies": {{
    "@types/chrome": "^0.0.325",
    "typescript": "^5.8.0"
  }},
  "packageManager": "{package_manager}"
}}
"""
        tsconfig_json = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM"],
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts"]
}
"""
        build_script_dir = project_dir / "scripts"
        build_script_dir.mkdir(parents=True, exist_ok=True)
        build_script_content = """import { cpSync, existsSync, mkdirSync, rmSync } from \"node:fs\"
import { spawnSync } from \"node:child_process\"
import { dirname, resolve } from \"node:path\"
import { fileURLToPath } from \"node:url\"

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const distDir = resolve(rootDir, "dist")

rmSync(distDir, { recursive: true, force: true })
mkdirSync(distDir, { recursive: true })

const npxCommand = process.platform === "win32" ? "npx.cmd" : "npx"
const compile = spawnSync(npxCommand, ["tsc", "--project", "tsconfig.json"], {
  cwd: rootDir,
  stdio: "inherit",
})

if (compile.status !== 0) {
  process.exit(compile.status ?? 1)
}

for (const asset of ["manifest.json", "popup.html"]) {
  const source = resolve(rootDir, "src", asset)
  if (existsSync(source)) {
    cpSync(source, resolve(distDir, asset))
  }
}
"""
        popup_script_name = "popup.ts"
        background_script_name = "background.ts"
        popup_script_content = """const status = document.querySelector('[data-role="status"]')

if (status instanceof HTMLElement) {
  const now = new Date().toLocaleTimeString()
  status.textContent = `Extension ready at ${now}`
}
"""
        background_script_content = """chrome.runtime.onInstalled.addListener(() => {
  console.log("Chrome extension installed.")
})
"""
        write_text_file(project_dir / "tsconfig.json", tsconfig_json)
        write_text_file(build_script_dir / "build-extension.mjs", build_script_content)
    else:
        package_json = f"""{{
  "name": "{package_name}",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {{
    "build": "node -e \"const fs=require('node:fs');fs.rmSync('dist',{{recursive:true,force:true}});fs.cpSync('src','dist',{{recursive:true}})\"",
    "dev": "node -e \"const fs=require('node:fs');fs.rmSync('dist',{{recursive:true,force:true}});fs.cpSync('src','dist',{{recursive:true}})\""
  }},
  "packageManager": "{package_manager}"
}}
"""
        popup_script_name = "popup.js"
        background_script_name = "background.js"
        popup_script_content = """const status = document.querySelector('[data-role="status"]')

if (status instanceof HTMLElement) {
  const now = new Date().toLocaleTimeString()
  status.textContent = `Extension ready at ${now}`
}
"""
        background_script_content = """chrome.runtime.onInstalled.addListener(() => {
  console.log("Chrome extension installed.")
})
"""

    readme_content = (
        f"# {project_name}\n\nGenerated by Vite Project Manager as a Chrome extension "
        f"({template}). Run `{package_manager} run build` before loading `dist/` as an unpacked extension.\n"
    )
    gitignore_content = "node_modules/\ndist/\n"

    write_text_file(project_dir / "package.json", package_json)
    write_text_file(project_dir / "README.md", readme_content)
    write_text_file(project_dir / ".gitignore", gitignore_content)
    write_text_file(src_dir / "manifest.json", manifest_content)
    write_text_file(src_dir / "popup.html", popup_html_content)
    write_text_file(src_dir / popup_script_name, popup_script_content)
    write_text_file(src_dir / background_script_name, background_script_content)


def scaffold_native_app_project(project_dir: Path, project_name: str, template: str) -> None:
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    if template == "C":
        entry_name = "main.c"
        entry_content = f"""#include <stdio.h>

int main(void) {{
    printf(\"Hello from {project_name}\\n\");
    return 0;
}}
"""
        build_hint = "gcc src/main.c -o build/app.exe"
    elif template == "C++":
        entry_name = "main.cpp"
        entry_content = f"""#include <iostream>

int main() {{
    std::cout << \"Hello from {project_name}\\n\";
    return 0;
}}
"""
        build_hint = "g++ src/main.cpp -o build/app.exe"
    else:
        entry_name = "Program.cs"
        entry_content = f"""Console.WriteLine(\"Hello from {project_name}\");
"""
        csproj_content = f"""<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <RootNamespace>{to_package_name(project_name).replace('-', '_')}</RootNamespace>
  </PropertyGroup>
</Project>
"""
        write_text_file(project_dir / f"{project_name}.csproj", csproj_content)
        build_hint = "dotnet run"

    readme_content = (
        f"# {project_name}\n\n"
        f"Generated by Vite Project Manager as a {template} starter app.\n\n"
        f"Build or run it with:\n\n"
        f"```\n{build_hint}\n```\n"
    )
    gitignore_content = "build/\nbin/\nobj/\n*.exe\n"

    write_text_file(project_dir / "README.md", readme_content)
    write_text_file(project_dir / ".gitignore", gitignore_content)
    write_text_file(src_dir / entry_name, entry_content)


def list_projects() -> list[Path]:
    ensure_projects_dir()
    return sorted(path for path in PROJECTS_DIR.iterdir() if path.is_dir())


def open_setup_shell(project_dir: Path, package_manager: str) -> None:
    package_manager_command, env = resolve_package_manager_command(package_manager)
    package_manager_path = package_manager_command[0]
    subprocess.Popen(
        ["cmd", "/k", f'cd /d "{project_dir}" && "{package_manager_path}" install'],
        cwd=project_dir,
        env=env,
    )


def open_project_shell(project_dir: Path) -> None:
    subprocess.Popen(["cmd", "/k", f'cd /d "{project_dir}"'], cwd=project_dir)


def open_project_in_vscode(project_dir: Path) -> None:
    for candidate in ("code.cmd", "code"):
        resolved = shutil.which(candidate)
        if resolved:
            subprocess.Popen([resolved, str(project_dir)], cwd=project_dir)
            return

    raise FileNotFoundError("VS Code command was not found on PATH.")


def is_path_inside(child: str | Path, parent: Path) -> bool:
    child_path = Path(child).resolve(strict=False)
    parent_path = parent.resolve(strict=False)
    try:
        child_path.relative_to(parent_path)
        return True
    except ValueError:
        return False


def find_processes_using_project(project_dir: Path) -> list[psutil.Process]:
    matches: list[psutil.Process] = []
    current_pid = os.getpid()

    for process in psutil.process_iter(["pid", "name", "cwd"]):
        pid = process.info.get("pid")
        if not pid or pid == current_pid:
            continue

        try:
            cwd = process.info.get("cwd")
            if cwd and is_path_inside(cwd, project_dir):
                matches.append(process)
                continue

            for opened in process.open_files() or []:
                if opened.path and is_path_inside(opened.path, project_dir):
                    matches.append(process)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue

    unique: dict[int, psutil.Process] = {}
    for process in matches:
        unique[process.pid] = process
    return list(unique.values())


def kill_processes_using_project(project_dir: Path) -> list[str]:
    killed: list[str] = []

    for process in find_processes_using_project(project_dir):
        try:
            name = process.name()
            pid = process.pid
            process.kill()
            process.wait(timeout=3)
            killed.append(f"{name} ({pid})")
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except (psutil.AccessDenied, psutil.TimeoutExpired, OSError):
            continue

    return killed


def force_remove_project(project_dir: Path) -> list[str]:
    try:
        shutil.rmtree(project_dir)
        return []
    except OSError:
        pass

    killed = kill_processes_using_project(project_dir)

    try:
        shutil.rmtree(project_dir)
        return killed
    except OSError:
        pass

    subprocess.run(
        ["cmd", "/c", "rmdir", "/s", "/q", str(project_dir)],
        check=False,
    )

    if project_dir.exists():
        raise OSError(f"Could not delete {project_dir}.")

    return killed


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ensure_projects_dir()

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Vite Project Manager")
        self.geometry("920x640")
        self.minsize(820, 560)

        self.project_paths: list[Path] = []
        self.is_creating = False
        self.clone_repo_window: ctk.CTkToplevel | None = None

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(19, weight=1)

        self.brand = ctk.CTkLabel(
            self.sidebar,
            text="Vite Project Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.brand.grid(row=0, column=0, padx=24, pady=(28, 8), sticky="w")

        self.subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Create and manage Vite, Electron, Node module, Chrome extension, and oddball native starter projects in one place.",
            wraplength=210,
            justify="left",
            text_color=("gray30", "gray75"),
        )
        self.subtitle.grid(row=1, column=0, padx=24, pady=(0, 18), sticky="w")

        self.project_name_label = ctk.CTkLabel(self.sidebar, text="New project name")
        self.project_name_label.grid(row=2, column=0, padx=24, pady=(0, 8), sticky="w")

        self.project_name_entry = ctk.CTkEntry(
            self.sidebar,
            placeholder_text="my-vite-app",
            width=212,
        )
        self.project_name_entry.grid(row=3, column=0, padx=24, pady=(0, 12), sticky="ew")

        self.package_manager_label = ctk.CTkLabel(self.sidebar, text="Package manager")
        self.package_manager_label.grid(row=4, column=0, padx=24, pady=(0, 8), sticky="w")

        self.package_manager_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=list(PACKAGE_MANAGERS),
        )
        self.package_manager_menu.grid(row=5, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.package_manager_menu.set("npm")

        self.node_template_label = ctk.CTkLabel(self.sidebar, text="Code template")
        self.node_template_label.grid(row=6, column=0, padx=24, pady=(0, 8), sticky="w")

        self.node_template_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=list(NODE_TEMPLATES),
        )
        self.node_template_menu.grid(row=7, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.node_template_menu.set("JavaScript")

        self.create_button = ctk.CTkButton(
            self.sidebar,
            text="Create Vite Project",
            command=self.start_create_vite_project,
        )
        self.create_button.grid(row=8, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.create_electron_button = ctk.CTkButton(
            self.sidebar,
            text="Create Electron App",
            fg_color="#1f6aa5",
            hover_color="#195480",
            command=self.start_create_electron_project,
        )
        self.create_electron_button.grid(row=9, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.create_node_button = ctk.CTkButton(
            self.sidebar,
            text="Create Node Module",
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self.start_create_node_module_project,
        )
        self.create_node_button.grid(row=10, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.create_chrome_button = ctk.CTkButton(
            self.sidebar,
            text="Create Chrome Extension",
            fg_color="#b45309",
            hover_color="#92400e",
            command=self.start_create_chrome_extension_project,
        )
        self.create_chrome_button.grid(row=11, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.nonsense_label = ctk.CTkLabel(
            self.sidebar,
            text="Nonsense category",
            text_color=("gray35", "gray70"),
        )
        self.nonsense_label.grid(row=12, column=0, padx=24, pady=(4, 8), sticky="w")

        self.native_template_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=list(NATIVE_TEMPLATES),
        )
        self.native_template_menu.grid(row=13, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.native_template_menu.set("C")

        self.create_native_button = ctk.CTkButton(
            self.sidebar,
            text="Create Native App",
            fg_color="#475569",
            hover_color="#334155",
            command=self.start_create_native_app_project,
        )
        self.create_native_button.grid(row=14, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.clone_chromium_button = ctk.CTkButton(
            self.sidebar,
            text="Clone Chromium",
            fg_color="#7c2d12",
            hover_color="#6b210c",
            command=self.start_clone_chromium,
        )
        self.clone_chromium_button.grid(row=15, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.clone_repo_button = ctk.CTkButton(
            self.sidebar,
            text="Clone Repo (tags)",
            fg_color="#3b0764",
            hover_color="#2c044d",
            command=self.open_clone_repo_window,
        )
        self.clone_repo_button.grid(row=16, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.refresh_button = ctk.CTkButton(
            self.sidebar,
            text="Refresh Projects",
            fg_color="transparent",
            border_width=1,
            command=self.refresh_projects,
        )
        self.refresh_button.grid(row=17, column=0, padx=24, pady=(0, 24), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.sidebar,
            text="Ready",
            wraplength=210,
            justify="left",
            text_color=("gray35", "gray70"),
        )
        self.status_label.grid(row=18, column=0, padx=24, pady=(12, 24), sticky="sw")

        self.content = ctk.CTkFrame(self, corner_radius=18)
        self.content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)

        self.header = ctk.CTkLabel(
            self.content,
            text="Managed Projects",
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        self.header.grid(row=0, column=0, padx=24, pady=(24, 6), sticky="w")

        self.header_text = ctk.CTkLabel(
            self.content,
            text="Projects live in ./projects/<name>. Select one to open a command prompt.",
            text_color=("gray35", "gray70"),
        )
        self.header_text.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        self.project_list = ctk.CTkScrollableFrame(self.content, corner_radius=14)
        self.project_list.grid(row=2, column=0, padx=24, pady=(0, 24), sticky="nsew")
        self.project_list.grid_columnconfigure(0, weight=1)

        self.refresh_projects()

    def set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def refresh_projects(self) -> None:
        self.project_paths = list_projects()

        for child in self.project_list.winfo_children():
            child.destroy()

        if not self.project_paths:
            empty = ctk.CTkLabel(
                self.project_list,
                text="No projects yet. Create one from the left panel.",
                text_color=("gray40", "gray70"),
            )
            empty.grid(row=0, column=0, padx=16, pady=18, sticky="w")
            self.set_status("No projects found.")
            return

        for index, project_path in enumerate(self.project_paths):
            card = ctk.CTkFrame(self.project_list, corner_radius=14)
            card.grid(row=index, column=0, padx=4, pady=6, sticky="ew")
            card.grid_columnconfigure(0, weight=1)

            name = ctk.CTkLabel(
                card,
                text=project_path.name,
                font=ctk.CTkFont(size=18, weight="bold"),
            )
            name.grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

            location = ctk.CTkLabel(
                card,
                text=str(project_path.relative_to(ROOT_DIR)),
                text_color=("gray40", "gray70"),
            )
            location.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")

            open_button = ctk.CTkButton(
                card,
                text="Open CMD",
                width=96,
                command=lambda path=project_path: self.handle_open_project(path),
            )
            open_button.grid(row=0, column=1, padx=(12, 8), pady=(16, 8), sticky="e")

            vscode_button = ctk.CTkButton(
                card,
                text="VS Code",
                width=96,
                command=lambda path=project_path: self.handle_open_vscode(path),
            )
            vscode_button.grid(row=0, column=2, padx=(0, 8), pady=(16, 8), sticky="e")

            edit_button = ctk.CTkButton(
                card,
                text="Edit",
                width=80,
                fg_color="transparent",
                border_width=1,
                command=lambda path=project_path: self.handle_rename_project(path),
            )
            edit_button.grid(row=1, column=1, padx=(12, 8), pady=(0, 16), sticky="e")

            delete_button = ctk.CTkButton(
                card,
                text="Delete",
                width=80,
                fg_color="#b42318",
                hover_color="#912018",
                command=lambda path=project_path: self.handle_delete_project(path),
            )
            delete_button.grid(row=1, column=2, padx=(0, 8), pady=(0, 16), sticky="e")

        self.set_status(f"Loaded {len(self.project_paths)} project(s).")

    def handle_open_project(self, project_path: Path) -> None:
        open_project_shell(project_path)
        self.set_status(f"Opened shell for {project_path.name}.")

    def handle_open_vscode(self, project_path: Path) -> None:
        try:
            open_project_in_vscode(project_path)
        except FileNotFoundError:
            messagebox.showerror("VS Code not found", "The 'code' command was not found on PATH.")
            self.set_status("VS Code command not found.")
            return

        self.set_status(f"Opened {project_path.name} in VS Code.")

    def handle_rename_project(self, project_path: Path) -> None:
        new_name = simpledialog.askstring(
            "Rename project",
            f"Enter a new name for '{project_path.name}':",
            initialvalue=project_path.name,
            parent=self,
        )
        if new_name is None:
            return

        try:
            cleaned_name = sanitize_name(new_name)
        except ValueError as error:
            messagebox.showerror("Invalid project name", str(error))
            return

        new_path = PROJECTS_DIR / cleaned_name
        if new_path == project_path:
            self.set_status(f"Name unchanged for {project_path.name}.")
            return
        if new_path.exists():
            messagebox.showerror("Project exists", "A project with that name already exists.")
            return

        try:
            project_path.rename(new_path)
        except OSError as error:
            messagebox.showerror("Rename failed", str(error))
            self.set_status(f"Could not rename {project_path.name}.")
            return

        self.refresh_projects()
        self.set_status(f"Renamed {project_path.name} to {cleaned_name}.")

    def handle_delete_project(self, project_path: Path) -> None:
        confirmed = messagebox.askyesno(
            "Delete project",
            f"Delete '{project_path.name}' and all of its files?",
            parent=self,
        )
        if not confirmed:
            return

        try:
            killed = force_remove_project(project_path)
        except OSError as error:
            messagebox.showerror(
                "Delete failed",
                f"Could not fully delete '{project_path.name}'.\n\n{error}",
            )
            self.set_status(f"Could not delete {project_path.name}.")
            return

        self.refresh_projects()
        if killed:
            self.set_status(f"Deleted {project_path.name} after killing {len(killed)} process(es).")
        else:
            self.set_status(f"Deleted {project_path.name}.")

    def start_create_vite_project(self) -> None:
        self.start_create_project(
            generator_label="Vite project",
            button_label="Create Vite Project",
        )

    def start_create_electron_project(self) -> None:
        self.start_create_project(
            generator_label="Electron app",
            button_label="Create Electron App",
        )

    def start_create_node_module_project(self) -> None:
        self.start_create_project(
            generator_label="Node module",
            button_label="Create Node Module",
            template=self.node_template_menu.get(),
        )

    def start_create_chrome_extension_project(self) -> None:
        self.start_create_project(
            generator_label="Chrome extension",
            button_label="Create Chrome Extension",
            template=self.node_template_menu.get(),
        )

    def start_create_native_app_project(self) -> None:
        self.start_create_project(
            generator_label="Native app",
            button_label="Create Native App",
            template=self.native_template_menu.get(),
        )

    def start_clone_chromium(self) -> None:
        if self.is_creating:
            return

        try:
            project_name = sanitize_name(self.project_name_entry.get())
        except ValueError as error:
            messagebox.showerror("Invalid project name", str(error))
            return

        project_dir = PROJECTS_DIR / project_name
        if project_dir.exists():
            messagebox.showerror("Project exists", "A project with that name already exists.")
            return

        self.is_creating = True
        self.create_button.configure(state="disabled")
        self.create_electron_button.configure(state="disabled")
        self.create_node_button.configure(state="disabled")
        self.create_chrome_button.configure(state="disabled")
        self.create_native_button.configure(state="disabled")
        self.clone_chromium_button.configure(state="disabled", text="Cloning...")
        self.package_manager_menu.configure(state="disabled")
        self.node_template_menu.configure(state="disabled")
        self.native_template_menu.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.set_status("Fetching Chromium tags from GitHub...")

        worker = threading.Thread(
            target=self.clone_chromium_worker,
            args=(project_name, project_dir),
            daemon=True,
        )
        worker.start()

    def open_clone_repo_window(self) -> None:
        if self.clone_repo_window is not None and self.clone_repo_window.winfo_exists():
            self.clone_repo_window.lift()
            return

        window = ctk.CTkToplevel(self)
        window.title("Clone GitHub Repo by Tag")
        window.geometry("520x360")
        window.resizable(False, False)
        self.clone_repo_window = window

        def on_close() -> None:
            self.clone_repo_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

        header = ctk.CTkLabel(
            window,
            text="Clone a GitHub repo at a specific tag",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        header.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 10), sticky="w")

        repo_label = ctk.CTkLabel(window, text="Repo (owner/name)")
        repo_label.grid(row=1, column=0, padx=20, pady=(4, 6), sticky="w")
        repo_entry = ctk.CTkEntry(window, placeholder_text="chromium/chromium", width=260)
        repo_entry.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="w")
        repo_entry.insert(0, CHROMIUM_REPO_SLUG)

        dest_label = ctk.CTkLabel(window, text="Destination folder name")
        dest_label.grid(row=3, column=0, padx=20, pady=(4, 6), sticky="w")
        dest_entry = ctk.CTkEntry(window, placeholder_text="my-clone", width=260)
        dest_entry.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="w")
        dest_entry.insert(0, "chromium-clone")

        tag_label = ctk.CTkLabel(window, text="Tag")
        tag_label.grid(row=5, column=0, padx=20, pady=(4, 6), sticky="w")
        tag_menu = ctk.CTkOptionMenu(window, values=["Loading..."], state="disabled", width=200)
        tag_menu.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="w")

        status = ctk.CTkLabel(window, text="Enter a repo and load tags.", text_color=("gray35", "gray70"))
        status.grid(row=7, column=0, columnspan=3, padx=20, pady=(6, 12), sticky="w")

        buttons_frame = ctk.CTkFrame(window, fg_color="transparent")
        buttons_frame.grid(row=8, column=0, columnspan=3, padx=20, pady=(8, 14), sticky="ew")
        buttons_frame.grid_columnconfigure(1, weight=1)

        load_button = ctk.CTkButton(buttons_frame, text="Load tags", width=110)
        load_button.grid(row=0, column=0, padx=(0, 8))
        clone_button = ctk.CTkButton(buttons_frame, text="Clone", width=110, state="disabled")
        clone_button.grid(row=0, column=2, padx=(8, 0))

        busy = {"loading": False, "cloning": False}

        def set_status(message: str, color: str = "gray35") -> None:
            status.configure(text=message, text_color=(color, color))

        def update_tags(tags: list[str]) -> None:
            if not tags:
                tag_menu.configure(values=["No tags found"], state="disabled")
                clone_button.configure(state="disabled")
                set_status("No tags found for this repo.", "#b42318")
                return
            tag_menu.configure(values=tags, state="normal")
            tag_menu.set(tags[0])
            clone_button.configure(state="normal")
            set_status(f"Loaded {len(tags)} tags.")

        def load_tags_thread(slug: str) -> None:
            tags = fetch_github_tags(slug, limit=None)
            window.after(0, lambda: update_tags(tags))
            busy["loading"] = False
            window.after(0, lambda: load_button.configure(state="normal", text="Load tags"))

        def on_load_tags() -> None:
            if busy["loading"] or busy["cloning"]:
                return
            try:
                slug = normalize_repo_slug(repo_entry.get())
            except ValueError as error:
                set_status(str(error), "#b42318")
                return
            busy["loading"] = True
            tag_menu.configure(values=["Loading..."], state="disabled")
            clone_button.configure(state="disabled")
            load_button.configure(state="disabled", text="Loading...")
            set_status("Fetching tags from GitHub...")
            threading.Thread(target=load_tags_thread, args=(slug,), daemon=True).start()

        def clone_thread(slug: str, tag: str, dest: Path) -> None:
            command = [
                "git",
                "clone",
                "--filter=blob:none",
                "--depth",
                "1",
                "--branch",
                tag,
                f"https://github.com/{slug}.git",
                str(dest),
            ]
            try:
                subprocess.run(command, check=True)
            except FileNotFoundError:
                if dest.exists() and not any(dest.iterdir()):
                    dest.rmdir()
                window.after(0, lambda: finish_clone(False, "Git not found on PATH."))
                return
            except subprocess.CalledProcessError as error:
                if dest.exists() and not any(dest.iterdir()):
                    dest.rmdir()
                window.after(0, lambda: finish_clone(False, f"Clone failed (exit {error.returncode})."))
                return

            window.after(0, lambda: finish_clone(True, f"Cloned {slug} at tag {tag} into {dest.name}."))

        def finish_clone(success: bool, message: str) -> None:
            busy["cloning"] = False
            clone_button.configure(state="normal", text="Clone")
            load_button.configure(state="normal")
            repo_entry.configure(state="normal")
            dest_entry.configure(state="normal")
            tag_menu.configure(state="normal")
            set_status(message, "#0f766e" if success else "#b42318")
            if success:
                self.refresh_projects()
                messagebox.showinfo("Repo cloned", message, parent=window)
                dest_entry.delete(0, "end")
            else:
                messagebox.showerror("Clone failed", message, parent=window)

        def on_clone() -> None:
            if busy["loading"] or busy["cloning"]:
                return
            dest_name = dest_entry.get().strip()
            tag = tag_menu.get().strip()

            try:
                slug = normalize_repo_slug(repo_entry.get())
            except ValueError as error:
                set_status(str(error), "#b42318")
                return

            if not tag or tag == "No tags found" or tag == "Loading...":
                set_status("Select a valid tag.", "#b42318")
                return
            try:
                cleaned_dest = sanitize_name(dest_name or slug.split("/")[-1])
            except ValueError as error:
                set_status(str(error), "#b42318")
                return

            dest_dir = PROJECTS_DIR / cleaned_dest
            if dest_dir.exists():
                set_status("Destination already exists.", "#b42318")
                return

            busy["cloning"] = True
            clone_button.configure(state="disabled", text="Cloning...")
            load_button.configure(state="disabled")
            repo_entry.configure(state="disabled")
            dest_entry.configure(state="disabled")
            tag_menu.configure(state="disabled")
            set_status(f"Cloning {slug} at tag {tag}...")

            threading.Thread(target=clone_thread, args=(slug, tag, dest_dir), daemon=True).start()

        load_button.configure(command=on_load_tags)
        clone_button.configure(command=on_clone)

        window.bind("<Return>", lambda _event: on_clone())

    def start_create_project(
        self,
        generator_label: str,
        button_label: str,
        template: str | None = None,
    ) -> None:
        if self.is_creating:
            return

        try:
            project_name = sanitize_name(self.project_name_entry.get())
        except ValueError as error:
            messagebox.showerror("Invalid project name", str(error))
            return

        project_dir = PROJECTS_DIR / project_name
        if project_dir.exists():
            messagebox.showerror("Project exists", "A project with that name already exists.")
            return

        package_manager = self.package_manager_menu.get()

        self.is_creating = True
        self.create_button.configure(state="disabled")
        self.create_electron_button.configure(state="disabled")
        self.create_node_button.configure(state="disabled")
        self.create_chrome_button.configure(state="disabled")
        self.create_native_button.configure(state="disabled")
        self.clone_chromium_button.configure(state="disabled")
        self.clone_repo_button.configure(state="disabled")
        self.package_manager_menu.configure(state="disabled")
        self.node_template_menu.configure(state="disabled")
        self.native_template_menu.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        if button_label == "Create Vite Project":
            self.create_button.configure(text="Creating...")
        elif button_label == "Create Electron App":
            self.create_electron_button.configure(text="Creating...")
        elif button_label == "Create Chrome Extension":
            self.create_chrome_button.configure(text="Creating...")
        elif button_label == "Create Native App":
            self.create_native_button.configure(text="Creating...")
        else:
            self.create_node_button.configure(text="Creating...")

        template_text = f" ({template})" if template else ""
        status_suffix = f" with {package_manager}" if generator_label != "Native app" else ""
        self.set_status(f"Creating {generator_label.lower()} {project_name}{template_text}{status_suffix}...")

        worker = threading.Thread(
            target=self.create_project_worker,
            args=(project_name, project_dir, generator_label, package_manager, template),
            daemon=True,
        )
        worker.start()

    def create_project_worker(
        self,
        project_name: str,
        project_dir: Path,
        generator_label: str,
        package_manager: str,
        template: str | None,
    ) -> None:
        project_dir.mkdir(parents=True, exist_ok=False)
        template_text = f" ({template})" if template else ""

        try:
            if generator_label == "Vite project":
                package_manager_command, env = resolve_package_manager_command(package_manager)
                command_args = ["create", "vite@latest", "."]
                subprocess.run(
                    package_manager_command + command_args,
                    cwd=project_dir,
                    check=True,
                    env=env,
                )
            elif generator_label == "Electron app":
                package_manager_command, env = resolve_package_manager_command(package_manager)
                command_args = ["create", "electron-app", "."]
                subprocess.run(
                    package_manager_command + command_args,
                    cwd=project_dir,
                    check=True,
                    env=env,
                )
            elif generator_label == "Chrome extension":
                scaffold_chrome_extension_project(
                    project_dir=project_dir,
                    project_name=project_name,
                    template=template or "JavaScript",
                    package_manager=package_manager,
                )
            elif generator_label == "Native app":
                scaffold_native_app_project(
                    project_dir=project_dir,
                    project_name=project_name,
                    template=template or "C",
                )
            else:
                scaffold_node_module_project(
                    project_dir=project_dir,
                    project_name=project_name,
                    template=template or "JavaScript",
                    package_manager=package_manager,
                )
        except FileNotFoundError:
            if not any(project_dir.iterdir()):
                project_dir.rmdir()
            self.after(
                0,
                lambda: self.finish_create_project(
                    success=False,
                    message=f"{package_manager} was not found. Make sure a Node.js version is installed and active through nvm.",
                ),
            )
            return
        except subprocess.CalledProcessError as error:
            if not any(project_dir.iterdir()):
                project_dir.rmdir()
            self.after(
                0,
                lambda: self.finish_create_project(
                    success=False,
                    message=f"{generator_label} creation failed with exit code {error.returncode}.",
                ),
            )
            return

        try:
            if generator_label == "Native app":
                open_project_shell(project_dir)
            else:
                open_setup_shell(project_dir, package_manager)
        except FileNotFoundError:
            missing_tool = "command prompt" if generator_label == "Native app" else package_manager
            self.after(
                0,
                lambda: self.finish_create_project(
                    success=False,
                    message=(
                        f"Project was created, but {missing_tool} could not be opened."
                        if generator_label == "Native app"
                        else f"Project was created, but {missing_tool} could not be found for the setup shell."
                    ),
                ),
            )
            return

        success_message = (
            f"Created {generator_label.lower()} {project_name}{template_text} and opened a command prompt."
            if generator_label == "Native app"
            else f"Created {generator_label.lower()} {project_name} with {package_manager} and opened setup shell."
        )
        self.after(
            0,
            lambda: self.finish_create_project(
                success=True,
                message=success_message,
            ),
        )

    def clone_chromium_worker(self, project_name: str, project_dir: Path) -> None:
        ensure_projects_dir()

        tags = fetch_github_tags(CHROMIUM_REPO_SLUG, limit=20)
        selected_tag = tags[0] if tags else None
        tag_text = f"tag {selected_tag}" if selected_tag else "default branch"

        command = [
            "git",
            "clone",
            "--filter=blob:none",
            "--depth",
            "1",
        ]
        if selected_tag:
            command.extend(["--branch", selected_tag])
        command.extend([CHROMIUM_REPO_URL, str(project_dir)])

        try:
            subprocess.run(command, check=True)
        except FileNotFoundError:
            if project_dir.exists() and not any(project_dir.iterdir()):
                project_dir.rmdir()
            self.after(
                0,
                lambda: self.finish_clone_chromium(
                    success=False,
                    message="Git was not found on PATH. Install Git to clone Chromium.",
                ),
            )
            return
        except subprocess.CalledProcessError as error:
            if project_dir.exists() and not any(project_dir.iterdir()):
                project_dir.rmdir()
            self.after(
                0,
                lambda: self.finish_clone_chromium(
                    success=False,
                    message=f"Cloning Chromium failed with exit code {error.returncode}.",
                ),
            )
            return

        tag_preview = ", ".join(tags[:5]) if tags else "no tags fetched"
        message = (
            f"Cloned Chromium ({tag_text}) into {project_name}. "
            f"Fetched tags: {tag_preview}."
        )
        self.after(
            0,
            lambda: self.finish_clone_chromium(
                success=True,
                message=message,
            ),
        )

    def finish_create_project(self, success: bool, message: str) -> None:
        self.is_creating = False
        self.create_button.configure(state="normal", text="Create Vite Project")
        self.create_electron_button.configure(state="normal", text="Create Electron App")
        self.create_node_button.configure(state="normal", text="Create Node Module")
        self.create_chrome_button.configure(state="normal", text="Create Chrome Extension")
        self.create_native_button.configure(state="normal", text="Create Native App")
        self.clone_chromium_button.configure(state="normal", text="Clone Chromium")
        self.clone_repo_button.configure(state="normal")
        self.package_manager_menu.configure(state="normal")
        self.node_template_menu.configure(state="normal")
        self.native_template_menu.configure(state="normal")
        self.refresh_button.configure(state="normal")
        self.set_status(message)

        if success:
            self.project_name_entry.delete(0, "end")
            self.refresh_projects()
            messagebox.showinfo("Project created", message)
        else:
            messagebox.showerror("Create failed", message)

    def finish_clone_chromium(self, success: bool, message: str) -> None:
        self.is_creating = False
        self.create_button.configure(state="normal", text="Create Vite Project")
        self.create_electron_button.configure(state="normal", text="Create Electron App")
        self.create_node_button.configure(state="normal", text="Create Node Module")
        self.create_chrome_button.configure(state="normal", text="Create Chrome Extension")
        self.create_native_button.configure(state="normal", text="Create Native App")
        self.clone_chromium_button.configure(state="normal", text="Clone Chromium")
        self.clone_repo_button.configure(state="normal")
        self.package_manager_menu.configure(state="normal")
        self.node_template_menu.configure(state="normal")
        self.native_template_menu.configure(state="normal")
        self.refresh_button.configure(state="normal")
        self.set_status(message)

        if success:
            self.project_name_entry.delete(0, "end")
            self.refresh_projects()
            messagebox.showinfo("Chromium cloned", message)
        else:
            messagebox.showerror("Clone failed", message)

if __name__ == "__main__":
    app = App()
    app.mainloop()
