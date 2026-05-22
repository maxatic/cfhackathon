"""Stdio entry point for Claude Desktop. Runs the same MCP server over stdio, no HTTP bridge."""
from erp_forecast.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
