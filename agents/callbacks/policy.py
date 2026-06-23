"""
agents/callbacks/policy.py
--------------------------
Role: Security layer and guardrails for the pipeline. Intercepts fetch tool
      responses before they enter session.state to ensure compliance.

Governed by: specs/SPEC.md Section 12.
"""

import logging
import os
import urllib.parse
from typing import Optional

import yaml
from google.adk.tools import BaseTool, ToolContext
from google.genai import Client

logger = logging.getLogger(__name__)

# Load blocklist at module level
_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "blocklist.yaml",
)
_blocked_domains = []
if os.path.exists(_config_path):
    with open(_config_path, "r", encoding="utf-8") as f:
        _blocklist_config = yaml.safe_load(f) or {}
        _blocked_domains = _blocklist_config.get("blocked_domains", [])


def _is_blocked_domain(domain: str) -> bool:
    """Checks if a domain ends with any blocked domain."""
    domain = domain.lower()
    for blocked in _blocked_domains:
        blocked = blocked.lower()
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False

def _append_policy_note(tool_context: ToolContext, msg: str):
    current_notes = tool_context.state.get("policy_notes", "")
    prefix = "\n" if current_notes else ""
    tool_context.state["policy_notes"] = current_notes + f"{prefix}- {msg}"


async def fetch_before_policy_callback(
    tool: BaseTool, args: dict, tool_context: ToolContext
) -> Optional[dict]:
    """
    before_tool_callback for the fetch tool.
    Implements structural checks (blocklist) and the hard fetch cap.
    """
    if tool.name != "fetch":
        return None

    url = args.get("url", "")
    if not url:
        return None

    # Enforce fetch cap
    fetch_count = tool_context.state.get("fetch_attempt_count", 0)
    if fetch_count >= 5:
        msg = f"{url} - skipped (fetch cap reached)"
        logger.warning("[Policy] %s", msg)
        _append_policy_note(tool_context, msg)
        return {"content": [{"type": "text", "text": "Content blocked: maximum fetch cap reached for this run."}]}

    # Increment counter
    tool_context.state["fetch_attempt_count"] = fetch_count + 1

    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.split(":")[0]

    # Blocklist check
    if _is_blocked_domain(domain):
        msg = f"{url} - blocked (blocklist)"
        logger.warning("[Policy] %s", msg)
        _append_policy_note(tool_context, msg)
        return {"content": [{"type": "text", "text": "Content blocked by structural policy (blocklisted domain)."}]}

    # Passes structural checks, continue to tool execution
    return None


async def fetch_after_policy_callback(
    tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: dict
) -> Optional[dict]:
    """
    after_tool_callback for the fetch tool.
    Implements the semantic policy check (ToU and PII).
    """
    if tool.name != "fetch":
        return None

    url = args.get("url", "")
    if not url:
        return None
        
    # If it was already blocked by the before_tool_callback or returned an error, it might not be a real fetch.
    content_text = ""
    if isinstance(tool_response, dict) and "content" in tool_response:
        for c in tool_response["content"]:
            if isinstance(c, dict) and c.get("type") == "text":
                content_text += c.get("text", "")

    if not content_text or "Content blocked" in content_text[:50]:
        return None # Already blocked by previous checks

    client = Client()
    # Fast/cheap model for semantic gating
    model = os.getenv("POLICY_CHECK_MODEL", "gemini-2.5-flash")

    prompt = f"""
    You are a strict security and policy enforcement scanner.
    Analyze the following scraped web content and determine if it violates our policies.
    
    Violations:
    1. Terms of Use (ToU): The content explicitly states that it may not be scraped, crawled, read by robots, or used by AI/automated systems.
    2. PII: The content contains highly sensitive Personally Identifiable Information (PII) like private email addresses, phone numbers, or SSNs that should not be ingested.

    Content to scan:
    ---
    {content_text[:10000]}
    ---

    If it violates the policy, explain why in one short sentence. 
    If it passes, output exactly 'PASS'.
    """

    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        result = resp.text.strip() if resp.text else "PASS"

        if result != "PASS":
            msg = f"{url} - blocked (ToU/PII)"
            logger.warning("[Policy] %s: %s", msg, result)
            _append_policy_note(tool_context, msg)
            return {"content": [{"type": "text", "text": f"Content blocked by semantic policy: {result}"}]}
        else:
            msg = f"{url} - fetched (ok)"
            _append_policy_note(tool_context, msg)
            
    except Exception as e:
        logger.error("[Policy] Semantic check failed to execute: %s", e)
        msg = f"{url} - blocked (scanner error)"
        _append_policy_note(tool_context, msg)
        return {"content": [{"type": "text", "text": "Content blocked due to policy scanner error."}]}

    # Passes both checks, return None to let the original content through
    return None
