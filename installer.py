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
SHERPA_SSE_URL = "http://sherpa.tp.int.percona.com:8400/sse"

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
    """Ask for a secret value (password) — input is hidden."""
    import getpass
    display_default = " [****]" if default else ""
    try:
        value = getpass.getpass(f"  {prompt}{display_default}: ").strip()
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
    print(f"  This gives Claude read-only access to ClickHouse (telemetry)")
    print(f"  and Elasticsearch (downloads) for VISTA reports.")
    print()
    print(f"  {BOLD}Two modes:{NC}")
    print(f"    1. {GREEN}Remote (recommended){NC} — connect to the shared Percona server")
    print(f"       No credentials needed. No local install. Just requires VPN when querying.")
    print(f"    2. {YELLOW}Local{NC} — run the MCP server on your machine with your own credentials")
    print(f"       No VPN needed, but you must have CH/ES credentials.")
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


def write_env_file(install_dir: Path, env: dict) -> Path:
    """Write credentials to .env file. Returns the path."""
    env_path = install_dir / ".env"
    lines = []
    for k, v in env.items():
        if v:
            lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n")
    # Restrict permissions — owner-only read/write
    env_path.chmod(0o600)
    info(f"Credentials saved to {env_path} (mode 600)")
    return env_path


def resolve_uv_path() -> str:
    """Find the full path to uv so Claude Desktop can locate it."""
    result = subprocess.run(["which", "uv"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    # Fallback: check common locations
    for candidate in [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ]:
        if candidate.exists():
            return str(candidate)
    return "uv"  # last resort, hope it's on PATH


def build_mcp_entry_local(install_dir: Path, env_path: Path) -> dict:
    uv = resolve_uv_path()
    return {
        "command": uv,
        "args": ["run", "--directory", str(install_dir), "mcp_server.py"],
        "env": {"DOTENV_PATH": str(env_path)},
    }


def build_mcp_entry_remote() -> dict:
    return {
        "command": "uvx",
        "args": ["mcp-proxy", SHERPA_SSE_URL],
    }


def configure_json_file(config_path: Path, mcp_entry: dict, label: str) -> bool:
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
    config["mcpServers"][MCP_SERVER_NAME] = mcp_entry

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    info(f"Configured {label}: {config_path}")
    return True


def configure_ai_clients(mcp_entry: dict) -> bool:
    print(c(BOLD, "Configuring AI clients..."))
    any_configured = False

    # Claude Desktop
    desktop_path = get_claude_desktop_config_path()
    if desktop_path is not None:
        if desktop_path.parent.exists():
            info("Claude Desktop detected — auto-configuring...")
            if configure_json_file(desktop_path, mcp_entry, "Claude Desktop"):
                any_configured = True
        else:
            print(f"  {DIM}Claude Desktop not detected ({desktop_path.parent}){NC}")
            if ask_yn("Configure Claude Desktop MCP anyway?", default=False):
                if configure_json_file(desktop_path, mcp_entry, "Claude Desktop"):
                    any_configured = True

    # Claude Code — settings.json
    code_settings_path = Path.home() / ".claude" / "settings.json"
    if code_settings_path.parent.exists():
        info("Claude Code detected — auto-configuring settings.json...")
        if configure_json_file(code_settings_path, mcp_entry, "Claude Code"):
            any_configured = True
    else:
        print(f"  {DIM}Claude Code not detected ({code_settings_path.parent}){NC}")
        if ask_yn("Configure Claude Code MCP anyway?", default=False):
            if configure_json_file(code_settings_path, mcp_entry, "Claude Code"):
                any_configured = True

    print()
    return any_configured

# ---------------------------------------------------------------------------
# Step 8: Install VISTA plugin
# ---------------------------------------------------------------------------

VISTA_PLUGIN_REPO = "https://github.com/Percona-Lab/VISTA"
VISTA_PLUGIN_ZIP_URL = f"{VISTA_PLUGIN_REPO}/releases/latest/download/vista-plugin.zip"


def get_claude_plugins_dir() -> Path | None:
    """Return the Claude Desktop plugins upload directory."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Linux":
        base = Path.home() / ".config" / "Claude"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata) / "Claude"
        else:
            return None
    else:
        return None

    # Find the cowork_plugins upload directory
    sessions_dir = base / "local-agent-mode-sessions"
    if not sessions_dir.exists():
        return None

    # Walk to find cowork_plugins/cache/local-desktop-app-uploads
    for session in sessions_dir.iterdir():
        for sub in session.iterdir():
            uploads = sub / "cowork_plugins" / "cache" / "local-desktop-app-uploads"
            if uploads.exists():
                return uploads
    return None


def install_vista_plugin() -> bool:
    """Download and install the VISTA plugin for Claude Desktop."""
    print(c(BOLD, "Installing VISTA plugin..."))

    plugins_dir = get_claude_plugins_dir()
    if plugins_dir is None:
        print(f"  {DIM}Claude Desktop plugin directory not found.{NC}")
        print(f"  {DIM}Install VISTA manually: {VISTA_PLUGIN_REPO}{NC}")
        return False

    vista_dir = plugins_dir / "vista" / "1.2.0"
    if vista_dir.exists():
        info("VISTA plugin already installed.")
        return True

    import tempfile
    import zipfile
    import urllib.request

    try:
        info(f"Downloading from {VISTA_PLUGIN_REPO}/releases/latest ...")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            urllib.request.urlretrieve(VISTA_PLUGIN_ZIP_URL, tmp.name)
            tmp_path = tmp.name

        vista_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(vista_dir)
        os.unlink(tmp_path)

        info("VISTA plugin installed!")
        print(f"  {DIM}For auto-updates, replace with the org marketplace version later.{NC}")
        return True
    except Exception as e:
        warn(f"Could not install VISTA plugin: {e}")
        print(f"  {DIM}Install manually: {VISTA_PLUGIN_REPO}{NC}")
        return False


# ---------------------------------------------------------------------------
# Step 9: Done
# ---------------------------------------------------------------------------

def print_done(any_clients_configured: bool, env: dict) -> None:
    print(c(BOLD, "=" * 60))
    print(c(GREEN + BOLD, " Installation complete!"))
    print(c(BOLD, "=" * 60))
    print()

    if any_clients_configured:
        print(f"  {YELLOW}Restart Claude Desktop / Claude Code for changes to take effect.{NC}")
        print()

    if not env:
        # Remote mode
        print(f"  {BOLD}Mode: Remote{NC}")
        print(f"  Connect to Percona VPN when querying, then try these prompts:")
        print()
        print(f"    /vista How many active instances of each product do we have?")
        print(f"    /vista Show me downloaded postgres packages by package type for last month")
        print(f"    /vista How is PSMDB adoption trending month over month?")
        print()
        print(f"  {DIM}To switch to local mode with your own credentials, re-run this installer.{NC}")
    else:
        sources = []
        if "CLICKHOUSE_HOST" in env:
            sources.append("ClickHouse")
        if "ES_HOST" in env:
            sources.append("Elasticsearch")

        if sources:
            print(f"  {BOLD}Mode: Local{NC} — configured: {', '.join(sources)}")
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
            print(f"  Re-run this installer to add credentials or switch to remote mode.")
            print()

    print(f"  Repo: https://github.com/Percona-Lab/vista-data-mcp")
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def choose_mode() -> str:
    """Ask user to choose remote (SHERPA) or local mode."""
    print(c(BOLD, "Connection mode"))
    print(f"  {GREEN}1) Remote (recommended){NC} — no credentials, no local install. Requires VPN when querying.")
    print(f"  {YELLOW}2) Local{NC} — run MCP server on your machine with your own CH/ES credentials. No VPN needed.")
    print()
    choice = ask("Choose mode", "1")
    print()
    return "remote" if choice != "2" else "local"


def main() -> None:
    print_banner()

    mode = choose_mode()

    if mode == "remote":
        # Remote mode — just configure the SSE URL, no local install needed
        print(c(BOLD, "Setting up remote connection..."))
        print(f"  Server: {SHERPA_SSE_URL}")
        print(f"  {DIM}No credentials needed. VPN required when running queries.{NC}")
        print()

        # Clean up any local .env credentials so only remote works
        local_env = Path.home() / PROJECT_SLUG / ".env"
        if local_env.exists():
            info("Removing local credentials (.env) — remote mode uses the shared server.")
            local_env.unlink()

        mcp_entry = build_mcp_entry_remote()
        any_configured = configure_ai_clients(mcp_entry)
        install_vista_plugin()
        print_done(any_configured, {})

    else:
        # Local mode — full install with credentials
        check_prerequisites()

        install_dir, is_rerun = get_install_dir()
        clone_or_pull(install_dir, is_rerun)
        setup_python(install_dir)

        env = collect_credentials()
        if env:
            env_path = write_env_file(install_dir, env)
        else:
            env_path = install_dir / ".env"
            if not env_path.exists():
                env_path.write_text("# Add credentials here and re-run the installer\n")

        mcp_entry = build_mcp_entry_local(install_dir, env_path)
        any_configured = configure_ai_clients(mcp_entry)
        install_vista_plugin()
        print_done(any_configured, env)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print(f"\n{YELLOW}  Installation cancelled.{NC}")
        sys.exit(1)
