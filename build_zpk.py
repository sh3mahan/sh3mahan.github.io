import argparse
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


@dataclass
class Project:
    base: Path

    @property
    def extract_dir(self) -> Path:
        return self.base / "_zpk_extract"

    @property
    def device_dir(self) -> Path:
        return self.extract_dir / "device"

    @property
    def app_side_zip(self) -> Path:
        return self.extract_dir / "app-side.zip"

    @property
    def build_dir(self) -> Path:
        return self.base / "_zpk_build"

    @property
    def device_zip(self) -> Path:
        return self.build_dir / "device.zip"

    @property
    def name(self) -> str:
        return self.base.name

    def zpk_files(self) -> list[Path]:
        return sorted(self.base.glob("*.zpk"))

    def default_zpk(self) -> Path:
        named = self.base / f"{self.name}.zpk"
        if named.is_file():
            return named

        files = self.zpk_files()
        if not files:
            raise SystemExit(f"No .zpk found in {self.base}")
        if len(files) > 1:
            names = ", ".join(p.name for p in files)
            raise SystemExit(
                f"Multiple .zpk files in {self.name}, specify path: {names}"
            )
        return files[0]

    def default_output(self) -> Path:
        return self.base / f"{self.name}.zpk"

    def is_ready_to_build(self) -> bool:
        return self.device_dir.is_dir() and self.app_side_zip.is_file()


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    OK = "✓"
    FAIL = "✗"
    DOT = "●"
    RING = "○"

    @classmethod
    def enable_windows_vt(cls) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            handle = ctypes.windll.kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 4)
        except OSError:
            pass

    @classmethod
    def use_color(cls) -> bool:
        return sys.stdout.isatty()


def c(text: str, *codes: str) -> str:
    if not Style.use_color():
        return text
    return "".join(codes) + text + Style.RESET


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def discover_projects(root: Path = SCRIPT_DIR) -> list[Project]:
    projects: list[Project] = []

    if list(root.glob("*.zpk")):
        projects.append(Project(root))

    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if list(entry.glob("*.zpk")):
            projects.append(Project(entry))

    return projects


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def project_status(project: Project) -> tuple[str, str]:
    if project.is_ready_to_build():
        return "ready", c(f"{Style.DOT} готов к сборке", Style.GREEN)
    if project.zpk_files():
        return "zpk", c(f"{Style.RING} есть .zpk", Style.YELLOW)
    return "empty", c(f"{Style.RING} нет .zpk", Style.DIM)


def zip_dir(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            files.sort()
            for name in files:
                full_path = Path(root) / name
                arcname = full_path.relative_to(source_dir).as_posix()
                zf.write(full_path, arcname)


def unpack_zpk(project: Project, zpk_path: Path | None = None) -> None:
    zpk_path = resolve_path(zpk_path) if zpk_path else project.default_zpk()
    if not zpk_path.is_file():
        raise SystemExit(f"ZPK not found: {zpk_path}")

    extract_dir = project.extract_dir
    device_dir = project.device_dir
    app_side_zip = project.app_side_zip

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    with zipfile.ZipFile(zpk_path) as zpk:
        names = set(zpk.namelist())
        required = {"app-side.zip", "device.zip"}
        missing = required - names
        if missing:
            raise SystemExit(
                f"Invalid zpk (missing {', '.join(sorted(missing))}): {zpk_path}"
            )

        zpk.extract("app-side.zip", extract_dir)

        device_dir.mkdir(parents=True)
        with zipfile.ZipFile(zpk.open("device.zip")) as device_zip:
            device_zip.extractall(device_dir)

    device_entries = sum(1 for p in device_dir.rglob("*") if p.is_file())
    print(c(f"{Style.OK} Распаковано", Style.GREEN, Style.BOLD))
    print(f"  {c('Источник:', Style.DIM)} {zpk_path.name}")
    print(f"  {c('Папка:', Style.DIM)}     {extract_dir}")
    print(f"  {c('Файлов:', Style.DIM)}    {device_entries}")


def build_zpk(project: Project, output_zpk: Path | None = None) -> Path:
    output = resolve_path(output_zpk) if output_zpk else project.default_output()

    if not project.device_dir.is_dir():
        raise SystemExit(f"Missing device dir: {project.device_dir}")
    if not project.app_side_zip.is_file():
        raise SystemExit(f"Missing app-side.zip: {project.app_side_zip}")

    zip_dir(project.device_dir, project.device_zip)

    project.build_dir.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zpk:
        zpk.write(project.app_side_zip, "app-side.zip")
        zpk.write(project.device_zip, "device.zip")

    size = output.stat().st_size
    print(c(f"{Style.OK} Собрано", Style.GREEN, Style.BOLD))
    print(f"  {c('Файл:', Style.DIM)}  {output}")
    print(f"  {c('Размер:', Style.DIM)} {format_size(size)}")
    return output


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def print_header() -> None:
    line = "═" * 52
    print(c(f"╔{line}╗", Style.CYAN))
    print(
        c("║", Style.CYAN)
        + c("        WatchFace ZPK Tool", Style.BOLD, Style.MAGENTA)
        + " " * 19
        + c("║", Style.CYAN)
    )
    print(c(f"╚{line}╝", Style.CYAN))
    print()


def print_box(title: str, lines: list[str]) -> None:
    width = max(len(title), *(len(line) for line in lines), 40) + 2
    print(c("┌─ " + title + " " + "─" * (width - len(title) - 3), Style.BLUE))
    for line in lines:
        print(c("│ ", Style.BLUE) + line + " " * (width - len(line)) + c("│", Style.BLUE))
    print(c("└" + "─" * width, Style.BLUE))
    print()


def ask_choice(prompt: str, max_value: int) -> int | None:
    while True:
        raw = input(c(f"{prompt} ", Style.CYAN, Style.BOLD)).strip()
        if raw.lower() in {"q", "quit", "exit", "0"}:
            return None
        if raw.isdigit():
            value = int(raw)
            if 0 <= value <= max_value:
                return value
        print(c("  Введите число от 0 до", Style.YELLOW), max_value)


def choose_project(projects: list[Project]) -> Project | None:
    if not projects:
        print(c("Проекты с .zpk не найдены.", Style.RED))
        return None

    print(c("Проекты:", Style.BOLD))
    print()
    for index, project in enumerate(projects, start=1):
        _, status = project_status(project)
        zpk_count = len(project.zpk_files())
        suffix = c(f" [{zpk_count} .zpk]", Style.DIM) if zpk_count > 1 else ""
        print(f"  {c(f'[{index}]', Style.CYAN, Style.BOLD)} {project.name}{suffix}")
        print(f"      {status}")
        print()

    print(f"  {c('[0]', Style.DIM)} Выход")
    print()
    choice = ask_choice("Выберите проект:", len(projects))
    if choice in (None, 0):
        return None
    return projects[choice - 1]


def choose_zpk(project: Project) -> Path | None:
    files = project.zpk_files()
    if len(files) == 1:
        return files[0]

    print(c("Доступные .zpk:", Style.BOLD))
    print()
    for index, zpk in enumerate(files, start=1):
        size = format_size(zpk.stat().st_size)
        marker = c(" (default)", Style.GREEN) if zpk.name == f"{project.name}.zpk" else ""
        print(
            f"  {c(f'[{index}]', Style.CYAN, Style.BOLD)} "
            f"{zpk.name} {c(f'— {size}', Style.DIM)}{marker}"
        )
    print()
    print(f"  {c('[0]', Style.DIM)} Назад")
    print()
    choice = ask_choice("Выберите .zpk:", len(files))
    if choice in (None, 0):
        return None
    return files[choice - 1]


def choose_action(project: Project) -> str | None:
    _, status = project_status(project)
    lines = [
        f"Проект: {c(project.name, Style.BOLD)}",
        f"Статус: {status}",
        f"Папка:  {c(str(project.base), Style.DIM)}",
    ]
    print_box("Текущий проект", lines)

    actions = [
        ("unpack", "Распаковать .zpk → _zpk_extract/"),
        ("build", "Собрать .zpk из _zpk_extract/"),
        ("repack", "Распаковать → Собрать"),
    ]

    print(c("Действия:", Style.BOLD))
    print()
    for index, (_, label) in enumerate(actions, start=1):
        print(f"  {c(f'[{index}]', Style.CYAN, Style.BOLD)} {label}")
    print()
    print(f"  {c('[0]', Style.DIM)} Назад")
    print()

    choice = ask_choice("Выберите действие:", len(actions))
    if choice in (None, 0):
        return None
    return actions[choice - 1][0]


def run_action(project: Project, action: str) -> None:
    print()
    if action == "unpack":
        zpk = choose_zpk(project)
        if zpk:
            unpack_zpk(project, zpk)
    elif action == "build":
        build_zpk(project)
    elif action == "repack":
        zpk = choose_zpk(project)
        if zpk:
            unpack_zpk(project, zpk)
            print()
            build_zpk(project)
    print()


def interactive_menu() -> None:
    Style.enable_windows_vt()
    projects = discover_projects()

    while True:
        clear_screen()
        print_header()
        project = choose_project(projects)
        if project is None:
            print(c("До встречи!", Style.DIM))
            return

        while True:
            clear_screen()
            print_header()
            action = choose_action(project)
            if action is None:
                break

            try:
                run_action(project, action)
            except SystemExit as exc:
                print(c(f"{Style.FAIL} {exc}", Style.RED, Style.BOLD))
                print()

            input(c("Enter — продолжить...", Style.DIM))


def cmd_unpack(args: argparse.Namespace) -> None:
    project = Project(resolve_path(args.project))
    zpk_path = resolve_path(args.zpk) if args.zpk else None
    unpack_zpk(project, zpk_path)


def cmd_build(args: argparse.Namespace) -> None:
    project = Project(resolve_path(args.project))
    build_zpk(project, args.output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unpack and build watchface .zpk archives.",
    )
    parser.add_argument(
        "-p",
        "--project",
        type=Path,
        default=Path("."),
        help="Project directory (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command")

    unpack_parser = subparsers.add_parser(
        "unpack",
        help="Extract .zpk into _zpk_extract/",
    )
    unpack_parser.add_argument(
        "zpk",
        nargs="?",
        type=Path,
        help="Path to .zpk (default: auto-detect in project folder)",
    )
    unpack_parser.set_defaults(func=cmd_unpack)

    build_parser_cmd = subparsers.add_parser(
        "build",
        help="Build .zpk from _zpk_extract/",
    )
    build_parser_cmd.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .zpk path (default: ./{project}.zpk)",
    )
    build_parser_cmd.set_defaults(func=cmd_build)

    return parser


def main() -> None:
    setup_stdio()

    if len(sys.argv) == 1:
        interactive_menu()
        return

    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        raise SystemExit(2)
    args.func(args)


if __name__ == "__main__":
    main()
