#!/usr/bin/env python3
"""Simple MCP server that executes shell commands via Python subprocess."""
import subprocess
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("python-exec")

@mcp.tool()
def run_command(cmd: str, cwd: str = r"C:\Users\63054\.agents\skills\daily-briefing-pro", timeout: int = 600) -> str:
    """Execute a shell command and return stdout + stderr."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, shell=True,
            capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
        if result.returncode != 0:
            output += f"\n--- EXIT CODE: {result.returncode} ---"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
