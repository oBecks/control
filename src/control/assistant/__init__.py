"""The Assistant (ADR 0005): the MCP server `Control.exe --mcp` runs, and Connect Claude, which writes
Claude's config so it starts that server."""

# Sent with every Engine call: the MCP server's version. Here rather than in server.py, so the Engine
# can read it without importing the MCP library.
MCP_HEADER = "X-Control-MCP"
