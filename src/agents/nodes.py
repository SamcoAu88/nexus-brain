"""
LangGraph Agent Nodes
Six node implementations for the Nexus-Brain reasoning pipeline.

Node flow:
  1. input_router       → Classify message type
  2. memory_retriever   → Search relevant memory
  3. entity_extractor   → Extract entities & detect PII
  4. reasoner           → Multi-step LLM reasoning with tools
  5. response_generator → Produce final response
  6. memory_writer      → Persist conversation & memory
"""

import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID
from copy import deepcopy

from src.agents.state import AgentState
from src.agents.tools import (
    search_memory,
    get_conversation_history,
    store_memory,
    get_entity_context,
    detect_pii,
    TOOL_DEFINITIONS,
)
from src.core.config import settings

logger = logging.getLogger(__name__)

# ─── LLM Client ─────────────────────────────────────────

# Use litellm for unified access to OpenAI / Anthropic
from litellm import completion

DEFAULT_MODEL = "deepseek/deepseek-chat"  # DeepSeek V4 Flash (fast & cheap)
REASONING_MODEL = "deepseek/deepseek-chat"  # Same model, DeepSeek is fast enough


def _call_llm(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    tools: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Unified LLM call wrapper."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Pass API key explicitly if DeepSeek is used
    if "deepseek" in model:
        kwargs["api_key"] = settings.DEEPSEEK_API_KEY
        kwargs["custom_llm_provider"] = "deepseek"
        # DeepSeek doesn't support tool calling in OpenAI format
        tools = None

    if tools:
        kwargs["tools"] = tools

    try:
        response = completion(**kwargs)
        choice = response.choices[0]

        result = {
            "content": choice.message.content or "",
            "tool_calls": [],
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        }

        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return result

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {
            "content": f"I encountered an error processing your request. Please try again.",
            "tool_calls": [],
            "model": model,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


# ─── Node 1: Input Router ──────────────────────────────

INPUT_CLASSIFIER_PROMPT = """You are an input classifier for Nexus-Brain, a personal AI assistant.

Classify the user's message into ONE of these types:
- question: The user is asking for information, help, or advice
- command: The user wants the system to perform an action
- memory: The user is sharing information to be remembered
- greeting: The user is saying hello or making small talk
- unknown: The message doesn't fit any category

Respond with ONLY a JSON object:
{"type": "question|command|memory|greeting|unknown", "confidence": 0.0-1.0, "reason": "brief explanation"}"""


def input_router(state: AgentState) -> Dict[str, Any]:
    """
    Classify the incoming message type.
    Sets input_type and input_confidence in state.
    """
    start = time.time()
    logger.info(f"🔄 [Node 1] Input Router: classifying message")

    result = _call_llm(
        system_prompt=INPUT_CLASSIFIER_PROMPT,
        user_message=state["input"],
        temperature=0.0,
        max_tokens=200,
    )

    import json

    classification = {"type": "unknown", "confidence": 0.0, "reason": "parse failed"}

    try:
        parsed = json.loads(result["content"])
        classification = {
            "type": parsed.get("type", "unknown"),
            "confidence": parsed.get("confidence", 0.0),
            "reason": parsed.get("reason", ""),
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse classifier output: {e}")

    logger.info(
        f"  → Classified as '{classification['type']}' "
        f"(confidence={classification['confidence']:.2f})"
    )

    tokens = result.get("usage", {})
    return {
        "input_type": classification["type"],
        "input_confidence": classification["confidence"],
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 2: Memory Retriever ──────────────────────────

MEMORY_QUERY_PROMPT = """Given the user's message and its classification, generate a concise search query
to find relevant information in the user's memory stores.

Return ONLY a JSON object:
{"query": "your search query here", "needs_context": true/false}"""


def memory_retriever(state: AgentState) -> Dict[str, Any]:
    """
    Retrieve relevant memories and conversation history.
    """
    start = time.time()
    input_type = state.get("input_type", "unknown")
    user_id = state["user_id"]
    conversation_id = state["conversation_id"]
    input_text = state["input"]

    logger.info(f"🔄 [Node 2] Memory Retriever: type={input_type}")

    # Always get conversation history for context
    history = get_conversation_history(conversation_id, limit=10)

    memories = []
    memory_query = None

    # Generate search query for questions and commands
    if input_type in ("question", "command"):
        query_result = _call_llm(
            system_prompt=MEMORY_QUERY_PROMPT,
            user_message=(
                f"Message type: {input_type}\n"
                f"Message: {input_text}\n"
                f"Conversation history: {len(history)} messages"
            ),
            temperature=0.0,
            max_tokens=150,
        )

        import json

        try:
            parsed = json.loads(query_result["content"])
            memory_query = parsed.get("query", input_text)
        except (json.JSONDecodeError, KeyError):
            memory_query = input_text

        # Search memories
        memories = search_memory(
            query=memory_query,
            user_id=user_id,
            limit=5,
        )

    logger.info(f"  → Retrieved {len(memories)} memories, {len(history)} history messages")
    if memory_query:
        logger.info(f"  → Search query: '{memory_query}'")

    tokens = query_result.get("usage", {}) if input_type in ("question", "command") else {}
    return {
        "retrieved_memory": memories,
        "conversation_history": history,
        "memory_query": memory_query,
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 3: Entity Extractor ──────────────────────────

ENTITY_EXTRACTOR_PROMPT = """Extract named entities from the user's message.

Entity types to detect: person, organization, location, date, concept, event, technology

Return ONLY a JSON array:
[
  {"name": "Entity Name", "type": "person|organization|location|date|concept|event|technology", "confidence": 0.0-1.0}
]"""


def entity_extractor(state: AgentState) -> Dict[str, Any]:
    """
    Extract entities and detect PII from the user input.
    """
    start = time.time()
    input_text = state["input"]

    logger.info("🔄 [Node 3] Entity Extractor")

    # 1. PII detection (using Presidio - already implemented)
    pii_result = detect_pii(input_text)

    # 2. Entity extraction via LLM (for non-PII entities)
    entities = []

    if input_text.strip():
        result = _call_llm(
            system_prompt=ENTITY_EXTRACTOR_PROMPT,
            user_message=input_text,
            temperature=0.0,
            max_tokens=300,
        )

        import json

        try:
            parsed = json.loads(result["content"])
            if isinstance(parsed, list):
                entities = [
                    e
                    for e in parsed
                    if isinstance(e, dict)
                    and e.get("name")
                    and e.get("type")
                ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Entity parsing failed: {e}")

    logger.info(
        f"  → PII: {'detected' if pii_result['has_pii'] else 'none'} "
        f"({pii_result['pii_types']}), "
        f"Entities: {len(entities)}"
    )

    tokens = result.get("usage", {})
    return {
        "entities": entities,
        "has_pii": pii_result["has_pii"],
        "pii_types": pii_result["pii_types"],
        "pii_masked_input": pii_result["masked_text"] if pii_result["has_pii"] else None,
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 4: Reasoner ──────────────────────────────────

REASONER_SYSTEM_PROMPT = """You are the reasoning engine of Nexus-Brain, a personal AI assistant.
Your job is to think step by step about how to best respond to the user.

Available context:
- User's message
- Message classification
- Relevant memory chunks
- Conversation history
- Known entities

You have tools available to search for more information or store memories.
Use them when you need more context or when the user shares important information.

Think carefully and produce:
1. Your assessment of what the user needs
2. Whether you need more information (via tools)
3. What the best response should contain"""

REASONER_USER_TEMPLATE = """Message: {input}
Type: {input_type}
Classification reason: {classification_reason}

Relevant memories:
{memories}

Recent conversation:
{history}

Known entities:
{entities}

PII detected: {has_pii}
PII types: {pii_types}

Instructions:
- Think step by step about what the user needs
- If you need more context, use search_memory
- If the user shared important info, use store_memory
- Always respond helpfully and concisely"""


def reasoner(state: AgentState) -> Dict[str, Any]:
    """
    Multi-step reasoning with tool access.
    """
    start = time.time()
    logger.info("🔄 [Node 4] Reasoner")

    memories_text = "\n".join(
        f"  [{i+1}] {m.get('content', '')[:300]}..."
        for i, m in enumerate(state.get("retrieved_memory", []))
    ) or "  (no relevant memories found)"

    history_text = "\n".join(
        f"  {m.get('role', '?')}: {m.get('content', '')[:200]}"
        for m in state.get("conversation_history", [])[-5:]
    ) or "  (no recent history)"

    entities_text = "\n".join(
        f"  {e.get('name', '?')} ({e.get('type', '?')})"
        for e in state.get("entities", [])
    ) or "  (no entities extracted)"

    user_message = REASONER_USER_TEMPLATE.format(
        input=state.get("pii_masked_input", state["input"]),
        input_type=state.get("input_type", "unknown"),
        classification_reason="",
        memories=memories_text,
        history=history_text,
        entities=entities_text,
        has_pii=state.get("has_pii", False),
        pii_types=", ".join(state.get("pii_types", [])),
    )

    result = _call_llm(
        system_prompt=REASONER_SYSTEM_PROMPT,
        user_message=user_message,
        model=REASONING_MODEL,
        temperature=0.3,
        max_tokens=2048,
        tools=TOOL_DEFINITIONS,
    )

    reasoning = result["content"]
    tool_calls = result.get("tool_calls", [])

    logger.info(f"  → Reasoning complete, {len(tool_calls)} tool calls")

    # Execute any tool calls
    executed_tools = []
    for tc in tool_calls:
        try:
            fn_name = tc["function"]["name"]
            import json

            args = json.loads(tc["function"]["arguments"])

            if fn_name == "search_memory":
                tc_result = search_memory(
                    query=args.get("query", state["input"]),
                    user_id=state["user_id"],
                    limit=args.get("limit", 5),
                )
                if tc_result:
                    # Merge into retrieved memory
                    existing_ids = {m.get("chunk_id") for m in state.get("retrieved_memory", [])}
                    new_results = [r for r in tc_result if r.get("chunk_id") not in existing_ids]
                    if new_results:
                        merged = deepcopy(state.get("retrieved_memory", []))
                        merged.extend(new_results)
                        state["retrieved_memory"] = merged

                executed_tools.append({"tool": "search_memory", "args": args, "results": len(tc_result)})

            elif fn_name == "store_memory":
                tc_result = store_memory(
                    content=args.get("content", ""),
                    user_id=state["user_id"],
                    title=args.get("title"),
                    importance=args.get("importance", 0.5),
                )
                executed_tools.append({"tool": "store_memory", "args": args, "source_id": tc_result})

            elif fn_name == "get_entity_context":
                tc_result = get_entity_context(
                    user_id=state["user_id"],
                    entity_types=args.get("entity_types"),
                    limit=args.get("limit", 10),
                )
                executed_tools.append({"tool": "get_entity_context", "args": args, "results": len(tc_result)})

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            executed_tools.append({"tool": fn_name, "error": str(e)})

    tokens = result.get("usage", {})
    return {
        "reasoning": reasoning,
        "tool_calls": executed_tools,
        "needs_clarification": "clarify" in reasoning.lower() or "more information" in reasoning.lower(),
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 5: Response Generator ────────────────────────

RESPONSE_PROMPT = """You are Nexus-Brain, a personal AI assistant. Generate a helpful, natural response.

Context:
- Message type: {input_type}
- User message: {input}
- Your reasoning: {reasoning}
- Retrieved memories: {memories}
- Entities detected: {entities}

Guidelines:
- Be concise but helpful (1-3 paragraphs max, or less)
- Reference relevant memories when answering questions
- Suggest next steps when appropriate
- If you need clarification, ask politely
- NEVER mention internal system details (nodes, state, tools)
- Sound natural and conversational"""


def response_generator(state: AgentState) -> Dict[str, Any]:
    """
    Generate the final response using all accumulated context.
    """
    start = time.time()
    logger.info("🔄 [Node 5] Response Generator")

    # If classified as greeting, short-circuit to a simple response
    if state.get("input_type") == "greeting":
        prompt = f"Respond naturally to this greeting: {state['input']}"
        result = _call_llm(
            system_prompt="You are Nexus-Brain, a friendly personal AI assistant. Keep responses warm and brief.",
            user_message=prompt,
            temperature=0.7,
            max_tokens=256,
        )

        tokens = result.get("usage", {})
        return {
            "response": result["content"],
            "model_used": result.get("model", DEFAULT_MODEL),
            "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
            "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
        }

    # For other types, use the full reasoning context
    memories_text = "\n".join(
        f"- {m.get('content', '')[:200]}"
        for m in state.get("retrieved_memory", [])[:3]
    ) or "None relevant"

    entities_text = ", ".join(
        f"{e.get('name', '?')} ({e.get('type', '?')})"
        for e in state.get("entities", [])
    ) or "None"

    # Build context for response generation
    user_input = state.get("pii_masked_input", state.get("input", ""))
    reasoning = state.get("reasoning", "")
    input_type = state.get("input_type", "unknown")

    # Create prompt - simpler and clearer
    user_prompt = f"""Input: {user_input}

Type: {input_type}
Reasoning: {reasoning if reasoning else "(no additional reasoning)"}
Relevant memories: {memories_text if memories_text != "None relevant" else "(no relevant memories)"}
Entities: {entities_text if entities_text != "None" else "(no entities)"}

Please provide a helpful response to the user's input."""

    result = _call_llm(
        system_prompt="You are Nexus-Brain, a helpful personal AI assistant. Be conversational, concise, and helpful. Never mention internal details.",
        user_message=user_prompt,
        model=REASONING_MODEL,
        temperature=0.5,
        max_tokens=1024,
    )

    response_text = result["content"] or "I understood your message but had trouble generating a response. Could you try asking again?"

    # Safety check: never send empty response
    if not response_text or response_text.strip() == "":
        response_text = "I received your message, but I'm having a bit of trouble forming a response right now. Could you rephrase or ask something else?"

    # If needs clarification, prefix with a clarification
    if state.get("needs_clarification") and not response_text.startswith("?"):
        response_text = response_text

    logger.info(f"  → Response generated ({len(response_text)} chars)")

    tokens = result.get("usage", {})
    return {
        "response": response_text,
        "model_used": result.get("model", REASONING_MODEL),
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 6: Memory Writer ─────────────────────────────

def memory_writer(state: AgentState) -> Dict[str, Any]:
    """
    Persist conversation and optionally store important memories.
    """
    start = time.time()
    logger.info("🔄 [Node 6] Memory Writer")

    memory_stored = False

    # Store as memory if user shared important information
    if state.get("input_type") in ("memory",) or (
        state.get("input_type") in ("question", "command")
        and any(
            kw in state["input"].lower()
            for kw in ["remember", "save", "store", "note", "important"]
        )
    ):
        source_id = store_memory(
            content=f"User: {state['input']}\nAssistant: {state.get('response', '')}",
            user_id=state["user_id"],
            title=f"Conversation Memory - {time.strftime('%Y-%m-%d %H:%M')}",
            source_type="agent",
            importance=0.6,
        )
        memory_stored = source_id is not None
        if memory_stored:
            logger.info(f"  → Memory stored: {source_id}")

    # If no response yet, create a fallback
    if not state.get("response"):
        logger.warning("  → No response generated, creating fallback")
        return {
            "memory_stored": memory_stored,
            "response": "I've processed your message. How can I help you further?",
            "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
        }

    return {
        "memory_stored": memory_stored,
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }
