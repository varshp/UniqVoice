"""
agents/mcp_tools.py
-------------------
Role: Loads MCP server configurations from config/mcp_servers.yaml and
      initializes ADK McpToolset instances. Logs discovered tools on startup
      to verify the handshake.

Governed by: specs/SPEC.md Section 9.
"""

import asyncio
import logging
import os
from typing import Dict

import yaml
from dotenv import load_dotenv
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

logger = logging.getLogger(__name__)

# Ensure .env is loaded (especially agents/.env where we copied TAVILY_API_KEY)
# In ADK, load_dotenv_for_agent typically does this, but we do it explicitly
# here so the module-level loading works.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

def _load_mcp_config() -> Dict[str, McpToolset]:
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "mcp_servers.yaml"
    )
    if not os.path.exists(config_path):
        logger.warning("MCP config not found at %s", config_path)
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    toolsets = {}
    for server in config.get("servers", []):
        name = server.get("name")
        command = server.get("command")
        args = server.get("args", [])
        env_keys = server.get("env", [])

        # Build environment for the MCP server
        server_env = os.environ.copy()
        for key in env_keys:
            val = os.getenv(key)
            if val:
                # mcp requires string values
                server_env[key] = str(val)
            else:
                logger.warning("MCP server '%s': %s not found in environment", name, key)

        mcp = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=command,
                    args=args,
                    env=server_env,
                )
            )
        )
        toolsets[name] = mcp
        
    return toolsets

# Load toolsets synchronously at module load
_mcp_toolsets = _load_mcp_config()

# Export specific toolsets
search_toolset = _mcp_toolsets.get("search")
fetch_toolset = _mcp_toolsets.get("fetch")

def verify_handshake_sync():
    """
    Connects to the MCP servers and logs their discovered tools to verify the handshake.
    Runs synchronously so it can be called during application startup.
    """
    async def _verify():
        for name, toolset in _mcp_toolsets.items():
            if toolset is None:
                continue
            try:
                tools = await toolset.get_tools()
                tool_names = [t.name for t in tools]
                logger.info("✅ MCP '%s' handshake successful. Tools: %s", name, tool_names)
                print(f"✅ MCP '{name}' handshake successful. Tools: {tool_names}")
            except Exception as e:
                logger.error("❌ MCP '%s' handshake failed: %s", name, e)
                print(f"❌ MCP '{name}' handshake failed: {e}")

    # If there's already a running event loop (e.g. within ADK's runner),
    # we shouldn't use asyncio.run. We handle both cases.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_verify())
    except RuntimeError:
        # No running loop, safe to run synchronously
        asyncio.run(_verify())

# Verify handshake on module import
verify_handshake_sync()
