"""Entry point for the Trackman Golf MCP server as a Claude Desktop extension.

The .mcpb bundle declares `trackman-mcp` as a dependency (see pyproject.toml);
the host installs it with uv and runs this launcher, which starts the same stdio
MCP server that `trackman-mcp` ships. All logic lives in the published package —
this file is just the entry point uv executes.
"""

from trackman_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
