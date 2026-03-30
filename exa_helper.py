"""
EXA Search helper for llama.cpp Research Center.

Provides function calling integration for web search capabilities.
"""

import os
import json
from typing import Optional

# EXA Search tool definition for function calling
EXA_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information. Use this when you need up-to-date facts, news, or information not in your training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information"
                }
            },
            "required": ["query"]
        }
    }
}


def get_exa_api_key() -> Optional[str]:
    """Get EXA API key from environment (injected via Modal Secret)."""
    return os.environ.get("EXA_API_KEY")


def search_web(query: str, num_results: int = 5) -> str:
    """
    Search the web using EXA Search API.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)
        
    Returns:
        Formatted string with search results
    """
    api_key = get_exa_api_key()
    if not api_key:
        return "ERROR: EXA API key not found. Please set EXA_API_KEY in Modal Secrets."
    
    try:
        from exa_py import Exa
        
        exa = Exa(api_key=api_key)
        results = exa.search_and_contents(
            query,
            text={"max_characters": 3000},
            highlights=True,
            type="auto",
            num_results=num_results
        )
        
        # Format results for LLM consumption
        formatted = []
        for i, result in enumerate(results.results, 1):
            title = result.title or "Untitled"
            text = result.text[:2000] if result.text else "No content available"
            url = result.url or ""
            formatted.append(f"[{i}] {title}\n{url}\n{text}\n")
        
        return "\n---\n".join(formatted)
        
    except Exception as e:
        return f"Search error: {str(e)}"


def handle_tool_call(tool_call: dict) -> dict:
    """
    Handle a tool call from the LLM and return the result.
    
    Args:
        tool_call: Tool call dict with 'function' and 'arguments'
        
    Returns:
        Dict with tool result in OpenAI format
    """
    function_name = tool_call.get("function", {}).get("name", "")
    arguments = tool_call.get("function", {}).get("arguments", "{}")
    
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    if function_name == "web_search":
        query = arguments.get("query", "")
        result = search_web(query)
        return {
            "role": "tool",
            "tool_call_id": tool_call.get("id", "unknown"),
            "content": result
        }
    
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id", "unknown"),
        "content": f"Unknown function: {function_name}"
    }


def get_tools_for_model(model_name: str) -> list:
    """
    Return appropriate tools based on model capabilities.
    
    Args:
        model_name: Name of the model
        
    Returns:
        List of tool definitions (empty if model doesn't support function calling)
    """
    # Models with known function calling support
    function_calling_models = [
        "qwen3.5", "qwen2.5", "qwen3",
        "llama-3.1", "llama-3.2", "llama-3.3", "llama-4",
        "deepseek-r1", "deepseek-v3",
        "hermes", "dolphin",
    ]
    
    model_lower = model_name.lower()
    for fc_model in function_calling_models:
        if fc_model in model_lower:
            return [EXA_SEARCH_TOOL]
    
    return []


def inject_search_context(query: str, user_message: str) -> str:
    """
    For models without function calling, inject search results directly into prompt.
    
    Args:
        query: Search query (can be same as user_message)
        user_message: Original user message
        
    Returns:
        Enhanced prompt with search context
    """
    search_results = search_web(query)
    
    return f"""Based on the following recent web search results:

{search_results}

---

User question: {user_message}

Provide a well-sourced answer based on the search results above. Cite sources using [1], [2], etc."""
