"""Entry point for the Trackman Golf MCP server as a Claude Desktop extension.

The .mcpb bundle declares `golf-coach` as a dependency (see pyproject.toml);
the host installs it with uv and runs this launcher, which starts the same stdio
MCP server that `golf-coach` ships. All logic lives in the published package —
this file is just the entry point uv executes.
"""

from golf_coach.server import mcp

if __name__ == "__main__":
    mcp.run()
