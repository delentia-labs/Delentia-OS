"""A tiny real MCP server (stdio) for the Round 61 persistent-connection tests: it counts calls and reports its own process id, so a test can see from the outside whether two calls
reached the same process (a reused session) or two different ones (a fresh session each time), and whether state leaked between two people."""
import os
import time

from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-counter")
_count = {"n": 0}


@server.tool()
def count() -> dict:
    """Count how many calls this server process has had (state between calls)."""
    _count["n"] += 1
    return {"calls_so_far": _count["n"], "pid": os.getpid()}


@server.tool()
def crash() -> dict:
    """Exit the server process immediately, as a server that dies would."""
    os._exit(1)


@server.tool()
def slow(seconds: float = 5.0) -> dict:
    """Sleep, then answer."""
    time.sleep(seconds)
    return {"slept": seconds, "pid": os.getpid()}


if __name__ == "__main__":
    server.run(transport="stdio")
