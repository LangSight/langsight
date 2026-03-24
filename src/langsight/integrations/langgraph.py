"""
LangGraph integration — now unified with the LangChain callback.

Since v0.4, LangSightLangGraphCallback is an alias for LangSightLangChainCallback.
The unified callback handles both LangChain and LangGraph automatically:
- Agent detection from graph names via on_chain_start
- Node-level context tracking
- Cross-ainvoke parent linking for multi-agent trees

Migration:
    # Before (v0.3):
    from langsight.integrations.langgraph import LangSightLangGraphCallback
    cb = LangSightLangGraphCallback(client=client, agent_name="my-graph")

    # After (v0.4) — same import still works:
    from langsight.integrations.langgraph import LangSightLangGraphCallback
    cb = LangSightLangGraphCallback(client=client, session_id=sid, trace_id=tid)

    # Or use the canonical import:
    from langsight.integrations.langchain import LangSightLangChainCallback
"""

from langsight.integrations.langchain import LangSightLangChainCallback, _fire_and_forget

# Backward-compatible alias
LangSightLangGraphCallback = LangSightLangChainCallback

__all__ = ["LangSightLangGraphCallback", "_fire_and_forget"]
