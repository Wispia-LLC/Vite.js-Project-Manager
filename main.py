from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import customtkinter as ctk
import psutil
from tkinter import messagebox, simpledialog


ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT_DIR / "projects"


def ensure_projects_dir() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def build_npm_env() -> dict[str, str]:
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


def resolve_npm_command() -> tuple[list[str], dict[str, str]]:
    env = build_npm_env()

    for candidate in ("npm.cmd", "npm"):
        resolved = shutil.which(candidate, path=env.get("PATH"))
        if resolved:
            return [resolved], env

    raise FileNotFoundError("npm was not found on PATH.")


def sanitize_name(name: str) -> str:
    cleaned = name.strip()
    invalid = '<>:"/\\|?*'
    if not cleaned:
        raise ValueError("Project name cannot be empty.")
    if any(char in invalid for char in cleaned):
        raise ValueError(f"Project name cannot contain any of: {invalid}")
    return cleaned


def list_projects() -> list[Path]:
    ensure_projects_dir()
    return sorted(path for path in PROJECTS_DIR.iterdir() if path.is_dir())


def open_setup_shell(project_dir: Path) -> None:
    npm_command, env = resolve_npm_command()
    npm_path = npm_command[0]
    subprocess.Popen(
        ["cmd", "/k", f'cd /d "{project_dir}" && "{npm_path}" install'],
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
        self.geometry("920x560")
        self.minsize(820, 500)

        self.project_paths: list[Path] = []
        self.is_creating = False

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        self.brand = ctk.CTkLabel(
            self.sidebar,
            text="Vite Project Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.brand.grid(row=0, column=0, padx=24, pady=(28, 8), sticky="w")

        self.subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Create and manage multiple Vite and Electron apps in one place.",
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

        self.create_button = ctk.CTkButton(
            self.sidebar,
            text="Create Vite Project",
            command=self.start_create_vite_project,
        )
        self.create_button.grid(row=4, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.create_electron_button = ctk.CTkButton(
            self.sidebar,
            text="Create Electron App",
            fg_color="#1f6aa5",
            hover_color="#195480",
            command=self.start_create_electron_project,
        )
        self.create_electron_button.grid(row=5, column=0, padx=24, pady=(0, 10), sticky="ew")

        self.refresh_button = ctk.CTkButton(
            self.sidebar,
            text="Refresh Projects",
            fg_color="transparent",
            border_width=1,
            command=self.refresh_projects,
        )
        self.refresh_button.grid(row=6, column=0, padx=24, pady=(0, 24), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.sidebar,
            text="Ready",
            wraplength=210,
            justify="left",
            text_color=("gray35", "gray70"),
        )
        self.status_label.grid(row=7, column=0, padx=24, pady=(12, 24), sticky="sw")

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
            command_args=["create", "vite@latest", "."],
            button_label="Create Vite Project",
        )

    def start_create_electron_project(self) -> None:
        self.start_create_project(
            generator_label="Electron app",
            command_args=["create", "electron-app", "."],
            button_label="Create Electron App",
        )

    def start_create_project(
        self,
        generator_label: str,
        command_args: list[str],
        button_label: str,
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

        self.is_creating = True
        self.create_button.configure(state="disabled")
        self.create_electron_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        if button_label == "Create Vite Project":
            self.create_button.configure(text="Creating...")
        else:
            self.create_electron_button.configure(text="Creating...")

        self.set_status(f"Creating {generator_label.lower()} {project_name}...")

        worker = threading.Thread(
            target=self.create_project_worker,
            args=(project_name, project_dir, generator_label, command_args),
            daemon=True,
        )
        worker.start()

    def create_project_worker(
        self,
        project_name: str,
        project_dir: Path,
        generator_label: str,
        command_args: list[str],
    ) -> None:
        project_dir.mkdir(parents=True, exist_ok=False)

        try:
            npm_command, env = resolve_npm_command()
            subprocess.run(
                npm_command + command_args,
                cwd=project_dir,
                check=True,
                env=env,
            )
        except FileNotFoundError:
            if not any(project_dir.iterdir()):
                project_dir.rmdir()
            self.after(
                0,
                lambda: self.finish_create_project(
                    success=False,
                    message="npm was not found. Make sure an nvm Node version is installed and active.",
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
            open_setup_shell(project_dir)
        except FileNotFoundError:
            self.after(
                0,
                lambda: self.finish_create_project(
                    success=False,
                    message="Project was created, but npm could not be found for the setup shell.",
                ),
            )
            return

        self.after(
            0,
            lambda: self.finish_create_project(
                success=True,
                message=f"Created {generator_label.lower()} {project_name} and opened setup shell.",
            ),
        )

    def finish_create_project(self, success: bool, message: str) -> None:
        self.is_creating = False
        self.create_button.configure(state="normal", text="Create Vite Project")
        self.create_electron_button.configure(state="normal", text="Create Electron App")
        self.refresh_button.configure(state="normal")
        self.set_status(message)

        if success:
            self.project_name_entry.delete(0, "end")
            self.refresh_projects()
            messagebox.showinfo("Project created", message)
        else:
            messagebox.showerror("Create failed", message)

if __name__ == "__main__":
    app = App()
    app.mainloop()
