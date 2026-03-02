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

Using reliable-ai's MCP implementation:

```python
from reliable_ai.mcp import MCPServerBase, create_tool
from typing import Any

class MyServer(MCPServerBase):
    def __init__(self) -> None:
        super().__init__(name="my-server", version="1.0.0")
        self._register_tools()

    def _register_tools(self) -> None:
        # Register each tool with its handler
        self.register_tool(
            create_tool(
                name="greet",
                description="Greet a user by name",
                parameters={
                    "name": {
                        "type": "string",
                        "description": "The name to greet",
                    },
                    "formal": {
                        "type": "boolean",
                        "description": "Use formal greeting",
                        "default": False,
                    },
                },
                required=["name"],
            ),
            handler=self._handle_greet,
        )

    async def _handle_greet(self, params: dict[str, Any]) -> str:
        name = params["name"]
        formal = params.get("formal", False)

        if formal:
            return f"Good day, {name}. How may I assist you?"
        return f"Hello, {name}!"

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "my-server": {
                "version": self.version,
                "tools": self.tool_names,
            }
        }
```

### Tool Definition Best Practices

```python
# Good: Clear, specific description
create_tool(
    name="search_files",
    description="Search for files matching a pattern in a directory. Returns list of matching file paths.",
    parameters={
        "pattern": {
            "type": "string",
            "description": "Glob pattern (e.g., '*.py', 'src/**/*.ts')",
        },
        "directory": {
            "type": "string",
            "description": "Directory to search in (defaults to current directory)",
            "default": ".",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return",
            "default": 100,
        },
    },
    required=["pattern"],
)

# Bad: Vague description
create_tool(
    name="search",
    description="Search stuff",  # Too vague!
    parameters={...},
)
```

### Filesystem Server Example

```python
from pathlib import Path
from reliable_ai.mcp import (
    FilesystemServer,
    FilePermission,
    PathConfig,
)

# Create sandboxed filesystem server
server = FilesystemServer(
    allowed_paths=["/home/user/workspace"],
    default_permissions=FilePermission.READ_WRITE,
)

# Add specific path with restricted permissions
server.add_allowed_path(
    "/home/user/sensitive",
    permissions=FilePermission.READ_ONLY,
)

# Available tools:
# - read_file: Read file contents
# - write_file: Write to file
# - list_directory: List directory contents
# - create_directory: Create new directory
# - delete: Delete file or directory
# - move: Move/rename file
# - copy: Copy file
# - get_file_info: Get file metadata
```

### API Proxy Server Example

```python
from reliable_ai.mcp import (
    APIProxyServer,
    EndpointConfig,
    HttpMethod,
    RateLimitConfig,
    RetryConfig,
    RetryStrategy,
)

# Create API proxy with auth and rate limiting
server = APIProxyServer(
    base_url="https://api.example.com/v1",
    auth_header="${API_KEY}",  # From environment
    rate_limit=RateLimitConfig(
        requests_per_minute=60,
        burst_limit=10,
    ),
    retry_config=RetryConfig(
        strategy=RetryStrategy.EXPONENTIAL,
        max_retries=3,
    ),
)

# Add typed endpoints
server.add_endpoint(EndpointConfig(
    path="/users/{user_id}",
    method=HttpMethod.GET,
    description="Get user by ID",
    parameters={
        "user_id": {"type": "string", "description": "User ID"},
    },
    cache_ttl=300,  # Cache for 5 minutes
))

server.add_endpoint(EndpointConfig(
    path="/users",
    method=HttpMethod.POST,
    description="Create a new user",
    parameters={
        "name": {"type": "string"},
        "email": {"type": "string"},
    },
    required_params=["name", "email"],
))
```

### Error Handling

```python
from reliable_ai.mcp import MCPError, MCPErrorCode

async def _handle_read_file(self, params: dict[str, Any]) -> str:
    path = Path(params["path"])

    # Permission check
    if not self._is_allowed_path(path):
        raise MCPError(
            MCPErrorCode.PERMISSION_DENIED,
            f"Access denied to path: {path}",
        )

    # File existence
    if not path.exists():
        raise MCPError(
            MCPErrorCode.RESOURCE_NOT_FOUND,
            f"File not found: {path}",
        )

    # Read file
    try:
        return path.read_text()
    except Exception as e:
        raise MCPError(
            MCPErrorCode.INTERNAL_ERROR,
            f"Failed to read file: {e}",
        )
```

## Advanced

### Scaffold New Servers

```python
from reliable_ai.mcp import scaffold_server, ServerSpec, ToolSpec

# Define server specification
spec = ServerSpec(
    name="database-server",
    description="MCP server for database operations",
    tools=[
        ToolSpec(
            name="query",
            description="Execute a read-only SQL query",
            parameters={
                "sql": {"type": "string", "description": "SQL query"},
                "limit": {"type": "integer", "default": 100},
            },
            required_params=["sql"],
        ),
        ToolSpec(
            name="list_tables",
            description="List all tables in the database",
            parameters={},
        ),
    ],
)

# Generate project
files = scaffold_server(spec, output_dir="./database-server")
# Creates: server.py, tests/, README.md
```

### Audit Logging

```python
server = MyServer(
    enable_audit_log=True,
    audit_log_path=Path("./logs/audit.log"),
)

# Access audit log
for entry in server.audit_log:
    print(f"{entry.timestamp}: {entry.method} - {'OK' if entry.success else 'FAIL'}")

# Get recent entries
recent = server.get_recent_audit(limit=10)
```

### Middleware

```python
from reliable_ai.mcp import MCPRequest, MCPResponse

async def logging_middleware(
    request: MCPRequest,
    next_handler,
) -> MCPResponse:
    print(f"Request: {request.method}")
    response = await next_handler(request)
    print(f"Response: {'success' if response.success else 'error'}")
    return response

async def auth_middleware(
    request: MCPRequest,
    next_handler,
) -> MCPResponse:
    token = request.metadata.get("auth_token")
    if not validate_token(token):
        return MCPResponse.error_response(
            MCPError(MCPErrorCode.PERMISSION_DENIED, "Invalid token"),
            request.id,
        )
    return await next_handler(request)

server.add_middleware(logging_middleware)
server.add_middleware(auth_middleware)
```

### Testing MCP Servers

```python
import pytest
from reliable_ai.mcp import MCPRequest

@pytest.fixture
def server():
    return MyServer()

@pytest.mark.asyncio
async def test_greet_tool(server):
    await server.start()

    response = await server.handle_request(MCPRequest(
        method="tools/call",
        params={
            "name": "greet",
            "arguments": {"name": "Alice"},
        },
    ))

    assert response.success is True
    assert "Alice" in str(response.result)

    await server.stop()

@pytest.mark.asyncio
async def test_invalid_tool(server):
    await server.start()

    response = await server.handle_request(MCPRequest(
        method="tools/call",
        params={"name": "nonexistent"},
    ))

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
