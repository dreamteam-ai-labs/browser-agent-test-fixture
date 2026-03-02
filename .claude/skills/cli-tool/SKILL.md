---
name: cli-tool
description: Command-line tool development with Python (argparse, click, typer) and best practices
version: 1.0.0
triggers:
  - cli
  - command line
  - terminal
  - argparse
  - click
  - typer
  - shell
  - script
  - console
tags:
  - python
  - cli
  - terminal
  - automation
---

# CLI Tool Development

## Summary

Python CLI tools should be:
- **User-friendly** - Clear help messages, intuitive arguments
- **Composable** - Work well with pipes and other tools
- **Robust** - Handle errors gracefully, validate inputs
- **Installable** - Distributable via pip with entry points

**Library comparison:**
| Library | Best For | Style |
|---------|----------|-------|
| argparse | Standard library, simple CLIs | Imperative |
| click | Complex CLIs, nested commands | Decorators |
| typer | Type hints, auto-completion | Type-based |

**Project structure:**
```
my-cli/
├── pyproject.toml    # Package config with entry points
├── src/
│   └── my_cli/
│       ├── __init__.py
│       ├── __main__.py   # Entry point
│       ├── cli.py        # CLI definition
│       ├── commands/     # Subcommand modules
│       └── utils.py
└── tests/
```

**Entry point (pyproject.toml):**
```toml
[project.scripts]
my-cli = "my_cli.cli:main"
```

## Details

### Typer (Recommended)

Modern, type-hint-based CLI framework:

```python
import typer
from pathlib import Path
from typing import Annotated, Optional

app = typer.Typer(help="My awesome CLI tool")

@app.command()
def process(
    input_file: Annotated[Path, typer.Argument(help="Input file path")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output path")] = Path("output.txt"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    count: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    """Process a file and generate output."""
    if verbose:
        typer.echo(f"Processing {input_file}...")

    if not input_file.exists():
        typer.echo(f"Error: {input_file} not found", err=True)
        raise typer.Exit(1)

    # Process file...
    typer.echo(f"✓ Wrote {output}")

@app.command()
def init(
    name: str,
    template: Annotated[str, typer.Option()] = "default",
) -> None:
    """Initialize a new project."""
    typer.echo(f"Creating {name} with {template} template...")

if __name__ == "__main__":
    app()
```

**Subcommand groups:**
```python
app = typer.Typer()
users_app = typer.Typer(help="User management")
app.add_typer(users_app, name="users")

@users_app.command("list")
def list_users() -> None:
    """List all users."""
    ...

@users_app.command("create")
def create_user(name: str) -> None:
    """Create a new user."""
    ...

# Usage: my-cli users list
#        my-cli users create "John"
```

### Click

Powerful decorator-based framework:

```python
import click

@click.group()
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """My CLI tool."""
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug

@cli.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--count", "-c", default=1, help="Number of times")
@click.pass_context
def process(ctx: click.Context, filename: str, count: int) -> None:
    """Process a file."""
    if ctx.obj["DEBUG"]:
        click.echo(f"Debug mode: processing {filename}")

    for _ in range(count):
        click.echo(f"Processing {filename}")

@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation")
def dangerous(yes: bool) -> None:
    """Perform a dangerous operation."""
    if not yes:
        click.confirm("Are you sure?", abort=True)
    click.echo("Done!")

if __name__ == "__main__":
    cli()
```

### Argparse (Standard Library)

Built-in, no dependencies:

```python
import argparse
import sys

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("input", help="Input file")
    parser.add_argument("-o", "--output", default="output.txt")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--count", type=int, default=1, choices=range(1, 101))

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    init_parser = subparsers.add_parser("init", help="Initialize project")
    init_parser.add_argument("name", help="Project name")

    args = parser.parse_args()

    if args.command == "init":
        print(f"Initializing {args.name}")
    else:
        if args.verbose:
            print(f"Processing {args.input}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Output and Formatting

**Rich for beautiful output:**
```python
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()

# Tables
table = Table(title="Users")
table.add_column("ID", style="cyan")
table.add_column("Name", style="green")
table.add_row("1", "Alice")
console.print(table)

# Progress bars
for item in track(items, description="Processing..."):
    process(item)

# Styled output
console.print("[bold red]Error:[/] File not found")
console.print("[green]✓[/] Success!")
```

### Configuration Files

```python
from pathlib import Path
import tomllib  # Python 3.11+

def load_config() -> dict:
    """Load config from standard locations."""
    config_paths = [
        Path.cwd() / ".mytool.toml",
        Path.home() / ".config" / "mytool" / "config.toml",
    ]

    for path in config_paths:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)

    return {}  # Defaults
```

## Advanced

### Testing CLIs

**CRITICAL: Use both unit AND integration tests!**

See [testing-strategy](../testing-strategy/SKILL.md) for the full explanation.

**Unit tests (tests/unit/)** - Test with injected dependencies:
```python
from typer.testing import CliRunner
from my_cli import app

runner = CliRunner()

def test_process_command():
    result = runner.invoke(app, ["process", "input.txt", "-v"])
    assert result.exit_code == 0
    assert "Processing" in result.stdout

def test_missing_file():
    result = runner.invoke(app, ["process", "nonexistent.txt"])
    assert result.exit_code == 1
    assert "not found" in result.stdout
```

**Integration tests (tests/integration/)** - Test real code paths:
```python
# tests/integration/test_cli_e2e.py
"""
Integration tests - run real CLI without mocked dependencies.

These catch bugs that unit tests miss, like initialization errors!
"""
from typer.testing import CliRunner
from my_cli.cli import app

runner = CliRunner()

def test_tasks_persist_across_invocations(tmp_path, monkeypatch):
    """
    Tasks created in one invocation should be visible in the next.

    This tests the REAL storage path, not an injected mock.
    """
    # Use real file storage in temp directory
    monkeypatch.chdir(tmp_path)

    # First invocation - add a task
    result1 = runner.invoke(app, ["add", "Buy milk"])
    assert result1.exit_code == 0

    # Second invocation - task should persist
    result2 = runner.invoke(app, ["list"])
    assert result2.exit_code == 0
    assert "Buy milk" in result2.output  # Would FAIL if get_store() was broken!

def test_config_file_loading(tmp_path, monkeypatch):
    """Test that config files are actually loaded."""
    monkeypatch.chdir(tmp_path)

    # Create a real config file
    config_file = tmp_path / ".mytool.toml"
    config_file.write_text('[settings]\nverbose = true\n')

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    # Verify config was loaded from real file
```

**Why both?**
- Unit tests are fast and test logic in isolation
- Integration tests catch initialization bugs (like `get_store()` returning wrong type)

### Shell Completion

**Typer auto-completion:**
```bash
# Generate completion script
my-cli --install-completion bash
my-cli --install-completion zsh

# Or manually
_MY_CLI_COMPLETE=bash_source my-cli > ~/.my-cli-complete.bash
echo "source ~/.my-cli-complete.bash" >> ~/.bashrc
```

### Stdin/Stdout Handling

```python
import sys
from typing import TextIO

@app.command()
def process(
    input_file: Annotated[typer.FileText, typer.Argument()] = sys.stdin,
    output_file: Annotated[typer.FileTextWrite, typer.Option("-o")] = sys.stdout,
) -> None:
    """Process input (file or stdin) to output (file or stdout)."""
    for line in input_file:
        output_file.write(line.upper())
```

### Signals and Graceful Shutdown

```python
import signal
import sys

def signal_handler(sig, frame):
    print("\nInterrupted, cleaning up...")
    # Cleanup code
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

### Distribution

**pyproject.toml:**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-cli"
version = "1.0.0"
dependencies = ["typer>=0.9", "rich>=13.0"]

[project.scripts]
my-cli = "my_cli:app"

[project.optional-dependencies]
dev = ["pytest", "pytest-cov"]
```

## Resources

- [Typer Docs](https://typer.tiangolo.com/)
- [Click Docs](https://click.palletsprojects.com/)
- [Rich Docs](https://rich.readthedocs.io/)
- [Python Packaging Guide](https://packaging.python.org/)
