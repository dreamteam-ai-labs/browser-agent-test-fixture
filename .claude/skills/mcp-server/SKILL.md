---
name: mcp-server
description: MCP (Model Context Protocol) server development for tool integration with LLMs
version: 1.0.0
triggers:
  - mcp
  - mcp server
  - model context protocol
  - tool server
  - claude tools
  - tool integration
tags:
  - python
  - mcp
  - tools
  - llm
  - integration
---

# MCP Server Development

## Summary

MCP (Model Context Protocol) enables LLMs to use external tools through standardized servers. Key concepts:

- **Tools** - Functions the LLM can call with structured parameters
- **Resources** - Data sources the LLM can read
- **Prompts** - Reusable prompt templates
- **Server** - Hosts tools and handles requests

**Project structure:**
```
mcp-server/
├── src/
│   └── my_server/
│       ├── __init__.py
│       ├── server.py     # Server implementation
│       ├── tools.py      # Tool definitions
│       └── handlers.py   # Tool handlers
├── tests/
├── pyproject.toml
└── README.md
```

**Key principles:**
1. Clear tool descriptions for LLM understanding
2. Structured input schemas with validation
3. Meaningful error messages
4. Audit logging for security
5. Sandboxed execution for safety

## Details

### Basic Server Structure

Using FastMCP (the standard Python MCP library):

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str, formal: bool = False) -> str:
    """Greet a user by name.

    Args:
        name: The name to greet
        formal: Use formal greeting
    """
    if formal:
        return f"Good day, {name}. How may I assist you?"
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

### Tool Definition Best Practices

```python
# Good: Clear docstring, typed parameters, descriptive names
@mcp.tool()
def search_files(pattern: str, directory: str = ".", max_results: int = 100) -> list[str]:
    """Search for files matching a glob pattern in a directory.

    Returns list of matching file paths.

    Args:
        pattern: Glob pattern (e.g., '*.py', 'src/**/*.ts')
        directory: Directory to search in (defaults to current directory)
        max_results: Maximum number of results to return
    """
    ...

# Bad: Vague description, unclear parameters
@mcp.tool()
def search(q: str) -> str:
    """Search stuff."""  # Too vague!
    ...
```

### Filesystem Operations Example

```python
from mcp.server.fastmcp import FastMCP
from pathlib import Path

mcp = FastMCP("filesystem-server")

ALLOWED_PATHS = [Path("/home/user/workspace")]

@mcp.tool()
def read_file(path: str) -> str:
    """Read file contents from an allowed path."""
    file_path = Path(path).resolve()
    if not any(file_path.is_relative_to(p) for p in ALLOWED_PATHS):
        raise ValueError(f"Access denied to path: {path}")
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return file_path.read_text()

@mcp.tool()
def list_directory(path: str = ".") -> list[str]:
    """List directory contents."""
    dir_path = Path(path).resolve()
    if not any(dir_path.is_relative_to(p) for p in ALLOWED_PATHS):
        raise ValueError(f"Access denied to path: {path}")
    return [str(p.name) for p in dir_path.iterdir()]
```

### Error Handling

```python
@mcp.tool()
def read_file(path: str) -> str:
    """Read file contents with proper error handling."""
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        return file_path.read_text()
    except PermissionError:
        raise ValueError(f"Permission denied: {path}")
    except Exception as e:
        raise RuntimeError(f"Failed to read file: {e}")
```

## Advanced

### Testing MCP Servers

```python
import pytest
from mcp.server.fastmcp import FastMCP

# Test your tool functions directly — they're just Python functions
def test_greet():
    result = greet("Alice")
    assert "Alice" in result

def test_greet_formal():
    result = greet("Alice", formal=True)
    assert "Good day" in result

    assert response.success is False
    assert response.error.code == MCPErrorCode.METHOD_NOT_FOUND

    await server.stop()
```

### Security Considerations

1. **Path validation** - Always resolve and validate paths
2. **Input sanitization** - Never trust user input
3. **Rate limiting** - Prevent abuse
4. **Audit logging** - Track all operations
5. **Permission model** - Principle of least privilege
6. **Sandboxing** - Restrict filesystem/network access

```python
def _validate_path(self, path: str) -> Path:
    """Safely validate and resolve a path."""
    resolved = Path(path).resolve()

    # Check against allowed paths
    for allowed in self.allowed_paths:
        if resolved.is_relative_to(allowed):
            return resolved

    raise MCPError(
        MCPErrorCode.PERMISSION_DENIED,
        f"Path not in allowed paths: {path}",
    )
```

## Resources

- [MCP Specification](https://modelcontextprotocol.io/)
- [reliable-ai MCP Module](../src/reliable_ai/mcp/)
- [Claude Tool Use Docs](https://docs.anthropic.com/en/docs/tool-use)
