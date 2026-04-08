#!/usr/bin/env python3
"""
VISTA Data MCP Installer — cross-platform installer for ClickHouse + Elasticsearch MCP server.
Run with: uv run installer.py
Part of the Alpine Toolkit, scaffolded with CAIRN.
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

if platform.system() == "Windows":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

REPO_URL = "https://github.com/Percona-Lab/vista-data-mcp.git"
PROJECT_SLUG = "vista-data-mcp"
PROJECT_NAME = "VISTA Data MCP"
MCP_SERVER_NAME = "vista-data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def c(color: str, text: str) -> str:
    return f"{color}{text}{NC}"


def info(msg: str) -> None:
    print(f"{GREEN}  {msg}{NC}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  Warning: {msg}{NC}")


def error(msg: str) -> None:
    print(f"{RED}  Error: {msg}{NC}")


def die(msg: str) -> None:
    error(msg)
    sys.exit(1)


def ask(prompt: str, default: str = "") -> str:
    display_default = f" [{default}]" if default else ""
    try:
        value = input(f"  {prompt}{display_default}: ").strip()
        return value if value else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_secret(prompt: str, default: str = "") -> str:
    """Ask for a secret value (password) — still echoes for simplicity."""
    display_default = " [****]" if default else ""
    try:
        value = input(f"  {prompt}{display_default}: ").strip()
        return value if value else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"  {prompt} ({hint}): ").strip().lower()
        if not value:
            return default
        return value in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def run(cmd: list, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check)

# ---------------------------------------------------------------------------
# Step 1: Banner
# ---------------------------------------------------------------------------

def print_banner() -> None:
    print()
    print(c(BOLD, "=" * 60))
    print(c(BOLD, " VISTA Data MCP Installer"))
    print(c(BOLD, " ClickHouse + Elasticsearch for Percona VISTA"))
    print(c(BOLD, "=" * 60))
    print()
    print(f"  This installs a read-only MCP server that gives Claude")
    print(f"  access to ClickHouse (telemetry) and Elasticsearch (downloads).")
    print(f"  Both data sources are optional — configure one or both.")
    print()

# ---------------------------------------------------------------------------
# Step 2: Check prerequisites
# ---------------------------------------------------------------------------

def check_prerequisites() -> None:
    print(c(BOLD, "Checking prerequisites..."))

    # Python check
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        die(f"Python 3.10+ required, found {major}.{minor}. Update Python and re-run.")
    info(f"Python {major}.{minor} found")

    # uv check
    try:
        result = subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        info(f"uv {result.stdout.strip()} found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        warn("uv is not installed. Installing uv...")
        try:
            subprocess.run(
                ["pip", "install", "uv"],
                check=True,
                capture_output=True,
            )
            info("uv installed via pip")
        except Exception:
            die(
                "Could not install uv. Install manually:\n"
                "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
                "Then re-run this installer."
            )

    # Git check
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        info("git found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        die("git is not installed. Install git and re-run.")

    print()

# ---------------------------------------------------------------------------
# Step 3: Install directory
# ---------------------------------------------------------------------------

def get_install_dir() -> tuple:
    print(c(BOLD, "Install location"))
    default = str(Path.home() / PROJECT_SLUG)
    raw = ask("Install directory", default)
    install_dir = Path(raw).expanduser().resolve()

    is_rerun = (install_dir / ".git").exists()
    if is_rerun:
        warn(f"Existing installation detected at {install_dir} — will update.")
    else:
        info(f"Will install to {install_dir}")

    print()
    return install_dir, is_rerun

# ---------------------------------------------------------------------------
# Step 4: Clone or pull
# ---------------------------------------------------------------------------

def clone_or_pull(install_dir: Path, is_rerun: bool) -> None:
    print(c(BOLD, "Setting up repository..."))

    if is_rerun:
        info(f"Pulling latest changes in {install_dir}")
        run(["git", "pull"], cwd=install_dir)
    else:
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        info(f"Cloning {REPO_URL}")
        run(["git", "clone", REPO_URL, str(install_dir)])

    print()

# ---------------------------------------------------------------------------
# Step 5: Install Python dependencies
# ---------------------------------------------------------------------------

def setup_python(install_dir: Path) -> None:
    print(c(BOLD, "Installing Python dependencies..."))

    info("Running uv sync...")
    run(["uv", "sync", "--quiet"], cwd=install_dir)

    info("Dependencies ready.")
    print()

# ---------------------------------------------------------------------------
# Step 6: Collect credentials
# ---------------------------------------------------------------------------

def collect_credentials() -> dict:
    """Prompt for ClickHouse and Elasticsearch connection details."""
    env = {}

    print(c(BOLD, "Data source credentials"))
    print(f"  {DIM}Both data sources are optional. Press Enter to skip any you don't have.{NC}")
    print()

    # ── ClickHouse ──────────────────────────────────────────────
    print(c(BOLD, "  ClickHouse (product telemetry)"))
    ch_host = ask("  Host", "")
    if ch_host:
        env["CLICKHOUSE_HOST"] = ch_host
        env["CLICKHOUSE_PORT"] = ask("  Port", "8443")
        env["CLICKHOUSE_USER"] = ask("  User", "default")
        env["CLICKHOUSE_PASSWORD"] = ask_secret("  Password")
        env["CLICKHOUSE_DATABASE"] = ask("  Database", "default")
        env["CLICKHOUSE_SECURE"] = ask("  Use HTTPS? (true/false)", "true")
        info("ClickHouse configured")
    else:
        print(f"  {DIM}Skipping ClickHouse — no host provided.{NC}")
    print()

    # ── Elasticsearch ───────────────────────────────────────────
    print(c(BOLD, "  Elasticsearch (product downloads)"))
    es_host = ask("  Host", "")
    if es_host:
        env["ES_HOST"] = es_host
        env["ES_PORT"] = ask("  Port", "9200")
        env["ES_USER"] = ask("  User", "")
        env["ES_PASSWORD"] = ask_secret("  Password")
        env["ES_SECURE"] = ask("  Use HTTPS? (true/false)", "true")
        env["ES_VERIFY_CERTS"] = ask("  Verify SSL certs? (true/false)", "true")
        info("Elasticsearch configured")
    else:
        print(f"  {DIM}Skipping Elasticsearch — no host provided.{NC}")
    print()

    if not env:
        warn("No data sources configured. You can add credentials later by re-running this installer.")

    return env

# ---------------------------------------------------------------------------
# Step 7: AI client configuration
# ---------------------------------------------------------------------------

def get_claude_desktop_config_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Linux":
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return None


def build_mcp_entry(install_dir: Path, env: dict) -> dict:
    entry = {
        "command": "uv",
        "args": ["run", "--directory", str(install_dir), "mcp_server.py"],
    }
    if env:
        entry["env"] = {k: v for k, v in env.items() if v}
    return entry


def configure_json_file(config_path: Path, install_dir: Path, env: dict, label: str) -> bool:
    if not config_path.parent.exists():
        if not ask_yn(f"{label} config dir not found at {config_path.parent}.\n  Configure anyway?", default=False):
            return False
        config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            warn(f"Could not parse {config_path}.")
            if not ask_yn(f"Overwrite {config_path}?", default=False):
                return False

    config.setdefault("mcpServers", {})
    config["mcpServers"][MCP_SERVER_NAME] = build_mcp_entry(install_dir, env)

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    info(f"Configured {label}: {config_path}")
    return True


def configure_ai_clients(install_dir: Path, env: dict) -> bool:
    print(c(BOLD, "Configuring AI clients..."))
    any_configured = False

    # Claude Desktop
    desktop_path = get_claude_desktop_config_path()
    if desktop_path is not None:
        if desktop_path.parent.exists():
            info("Claude Desktop detected — auto-configuring...")
            if configure_json_file(desktop_path, install_dir, env, "Claude Desktop"):
                any_configured = True
        else:
            print(f"  {DIM}Claude Desktop not detected ({desktop_path.parent}){NC}")
            if ask_yn("Configure Claude Desktop MCP anyway?", default=False):
                if configure_json_file(desktop_path, install_dir, env, "Claude Desktop"):
                    any_configured = True

    # Claude Code — settings.json
    code_settings_path = Path.home() / ".claude" / "settings.json"
    if code_settings_path.parent.exists():
        info("Claude Code detected — auto-configuring settings.json...")
        if configure_json_file(code_settings_path, install_dir, env, "Claude Code"):
            any_configured = True
    else:
        print(f"  {DIM}Claude Code not detected ({code_settings_path.parent}){NC}")
        if ask_yn("Configure Claude Code MCP anyway?", default=False):
            if configure_json_file(code_settings_path, install_dir, env, "Claude Code"):
                any_configured = True

    print()
    return any_configured

# ---------------------------------------------------------------------------
# Step 8: Done
# ---------------------------------------------------------------------------

def print_done(any_clients_configured: bool, env: dict) -> None:
    print(c(BOLD, "=" * 60))
    print(c(GREEN + BOLD, " Installation complete!"))
    print(c(BOLD, "=" * 60))
    print()

    if any_clients_configured:
        print(f"  {YELLOW}Restart Claude Desktop / Claude Code for changes to take effect.{NC}")
        print()

    sources = []
    if "CLICKHOUSE_HOST" in env:
        sources.append("ClickHouse")
    if "ES_HOST" in env:
        sources.append("Elasticsearch")

    if sources:
        print(f"  Configured data sources: {', '.join(sources)}")
        print()
        print(f"  {BOLD}Try these prompts after restarting:{NC}")
        if "ES_HOST" in env:
            print(f"    /vista Show me downloaded postgres packages by package type for last month")
        if "CLICKHOUSE_HOST" in env:
            print(f"    /vista How many active PS 8.4 instances are there?")
            print(f"    /vista What's the version distribution for PXC?")
        print()
    else:
        print(f"  No data sources configured yet.")
        print(f"  Re-run this installer to add ClickHouse or Elasticsearch credentials.")
        print()

    print(f"  To update later: re-run this installer from the same directory.")
    print(f"  Repo: https://github.com/Percona-Lab/vista-data-mcp")
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print_banner()
    check_prerequisites()

    install_dir, is_rerun = get_install_dir()
    clone_or_pull(install_dir, is_rerun)
    setup_python(install_dir)

    env = collect_credentials()
    any_configured = configure_ai_clients(install_dir, env)
    print_done(any_configured, env)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(f"\n{YELLOW}  Installation cancelled.{NC}")
        sys.exit(1)
