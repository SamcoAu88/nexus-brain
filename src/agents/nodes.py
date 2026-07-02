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
from datetime import datetime

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

# Dynamic current date for system prompts
CURRENT_DATE = datetime.now().strftime("%B %d, %Y")  # e.g., "June 30, 2026"
CURRENT_DATE_ISO = datetime.now().strftime("%Y-%m-%d")  # e.g., "2026-06-30"

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

    Short confirmations ('yes please', 'hayır') are detected WITHOUT an LLM
    call and classified as 'confirmation' — they answer the assistant's own
    previous message, so treating them as greetings/unknown breaks context.
    """
    start = time.time()
    logger.info(f"🔄 [Node 1] Input Router: classifying message")

    # Fast path: bare yes/no answers refer to the previous assistant message
    try:
        from src.tasks.agent_tasks import _detect_confirmation

        if _detect_confirmation(state["input"]):
            logger.info("  → Classified as 'confirmation' (fast path, answers previous message)")
            return {
                "input_type": "confirmation",
                "input_confidence": 0.95,
                "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
            }
    except Exception as e:
        logger.warning(f"Confirmation fast-path failed: {e}")

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
    Handles special cases like "What do you know about me?" by loading all user memories.
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
    query_result = {}  # Initialize to prevent NameError

    # Check for "about me" type queries - load ALL user memories
    about_me_keywords = [
        "what do you know about me",
        "what do you remember about me",
        "tell me what you know about me",
        "what information do you have about me",
        "who am i",
        "what have i told you",
        "what can you tell me about myself",
        "what do you know about me so far",  # Added
        "what else do you know",  # Added
        "tell me about myself",  # Added
        "what have you learned about me",  # Added
    ]

    is_about_me = any(keyword in input_text.lower() for keyword in about_me_keywords)

    # "About me" is a LISTING request, not a search: fetch the user's most
    # recent memories directly. Works regardless of input_type because the
    # router sometimes classifies "Who am I?" as a greeting.
    if is_about_me:
        try:
            from src.agents.tools import get_recent_memories

            memory_query = "(recent memories listing)"
            memories = get_recent_memories(user_id=user_id, limit=15)
            logger.info(f"  → 'About me' query: listed {len(memories)} recent memories directly")
        except Exception as e:
            logger.error(f"Recent memories listing failed: {e}")
            memories = []

    # For other questions/commands, generate a search query and run hybrid search
    elif input_type in ("question", "command"):
        try:
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
            except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
                logger.warning(f"Query parsing failed: {parse_err}, using input text")
                memory_query = input_text

            try:
                memories = search_memory(
                    query=memory_query,
                    user_id=user_id,
                    limit=5,
                )
            except Exception as search_err:
                logger.error(f"Memory search failed: {search_err}, continuing with empty memories")
                memories = []

        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            memories = []
            query_result = {}

    logger.info(f"  → Retrieved {len(memories)} memories, {len(history)} history messages")
    if memory_query:
        logger.info(f"  → Search query: '{memory_query}'")

    tokens = query_result.get("usage", {}) if query_result else {}
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

    # 1. PII detection AND masking (using Presidio - already implemented)
    from src.security.pii import process_pii
    pii_result = process_pii(input_text, mask=True)

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
        "pii_masked_input": pii_result["masked"],  # Correct key from process_pii()
        "tokens_used": state.get("tokens_used", 0) + tokens.get("total_tokens", 0),
        "latency_ms": state.get("latency_ms", 0.0) + (time.time() - start) * 1000,
    }


# ─── Node 4: Reasoner ──────────────────────────────────

REASONER_SYSTEM_PROMPT = f"""You are the reasoning engine of Nexus-Brain, a personal AI assistant.
Your job is to think step by step about how to best respond to the user.

📅 TODAY'S DATE: {CURRENT_DATE} ({CURRENT_DATE_ISO})

Available context:
- User's message
- Message classification
- Relevant memory chunks from user's history
- Conversation history
- Known entities about the user
- Web search access for current information

MEMORY USAGE:
- Always reference what you know about the user
- Personalize responses using stored memories
- If asked "What do you know about me?", compile all stored information

You have tools available to search for more information or store memories.
Use them when you need current information or when the user shares important information.

Think carefully and produce:
1. Your assessment of what the user needs
2. Whether you need web search for current/recent information
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
    Multi-step reasoning with tool access and optional web search.

    IMPORTANT: Retrieved memories are NOT masked again because:
    - They are already from the user's own database
    - User info (name, location, etc.) is intentionally stored and should be used
    - Masking them would lose context the user explicitly saved
    """
    start = time.time()
    logger.info("🔄 [Node 4] Reasoner")

    # Check if web search is needed for current information
    from src.tools.search import needs_web_search, web_search
    user_input = state.get("input", "")
    web_context = ""
    calendar_context = ""

    if needs_web_search(user_input):
        logger.info("  → Fetching current information via web search...")
        try:
            web_context = web_search(user_input)
            logger.info(f"  → Web context retrieved ({len(web_context)} chars)")
        except Exception as e:
            logger.warning(f"Web search failed: {e}")
            web_context = ""

    # Check if the user is asking about their calendar/schedule
    try:
        from src.tools.calendar import needs_calendar, list_upcoming_events, format_events_for_context

        if needs_calendar(user_input):
            logger.info("  → Fetching Google Calendar events...")
            events = list_upcoming_events(days=30, max_results=20)
            calendar_context = format_events_for_context(events)
            logger.info(f"  → Calendar: {len(events)} events injected into context (30-day horizon)")
    except Exception as e:
        logger.warning(f"Calendar fetch failed: {e}")
        calendar_context = ""

    # Build memories text with safe extraction (no PII masking on retrieved memories!)
    # Memories from DB should be used AS-IS to preserve user context
    memories_list = state.get("retrieved_memory", [])
    memories_parts = []

    for i, m in enumerate(memories_list):
        try:
            # Safely extract content from memory dict/object
            if isinstance(m, dict):
                content = m.get("content", "")
            else:
                content = str(m)

            if content:
                # Truncate but don't mask - this is already stored user info
                truncated = str(content)[:300]
                memories_parts.append(f"  [{i+1}] {truncated}...")
        except Exception as e:
            logger.warning(f"Failed to extract memory {i}: {e}")
            continue

    memories_text = "\n".join(memories_parts) or "  (no relevant memories found)"

    # Build conversation history text with safe extraction
    history_list = state.get("conversation_history", [])[-5:]
    history_parts = []

    for m in history_list:
        try:
            if isinstance(m, dict):
                role = m.get("role", "?")
                content = m.get("content", "")
            else:
                role = "?"
                content = str(m)

            if content:
                truncated = str(content)[:200]
                history_parts.append(f"  {role}: {truncated}")
        except Exception as e:
            logger.warning(f"Failed to extract history message: {e}")
            continue

    history_text = "\n".join(history_parts) or "  (no recent history)"

    # Build entities text with safe extraction
    entities_list = state.get("entities", [])
    entities_parts = []

    for e in entities_list:
        try:
            if isinstance(e, dict):
                name = e.get("name", "?")
                etype = e.get("type", "?")
                entities_parts.append(f"  {name} ({etype})")
        except Exception as err:
            logger.warning(f"Failed to extract entity: {err}")
            continue

    entities_text = "\n".join(entities_parts) or "  (no entities extracted)"

    # Build enhanced prompt with web context if available
    # IMPORTANT: Use ORIGINAL input (not masked) so LLM understands user's actual intent
    # User names, locations, and context must be visible to reasoning engine
    user_message = REASONER_USER_TEMPLATE.format(
        input=state["input"],
        input_type=state.get("input_type", "unknown"),
        classification_reason="",
        memories=memories_text,
        history=history_text,
        entities=entities_text,
        has_pii=state.get("has_pii", False),
        pii_types=", ".join(state.get("pii_types", [])),
    )

    # Append web context if available
    if web_context:
        user_message = f"{user_message}\n\nCurrent Information from Web:\n{web_context}"

    # Append calendar context if available
    if calendar_context:
        user_message = f"{user_message}\n\nUser's Google Calendar (next 30 days):\n{calendar_context}"

    result = _call_llm(
        system_prompt=REASONER_SYSTEM_PROMPT,
        user_message=user_message,
        model=REASONING_MODEL,
        temperature=0.3,
        max_tokens=2048,
        tools=None,  # DeepSeek doesn't support tools, web search is done before LLM call
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

RESPONSE_PROMPT = f"""You are Nexus-Brain, a personal AI assistant. Generate a helpful, natural response.

📅 Today: {CURRENT_DATE}

Context:
- Message type: {{input_type}}
- User message: {{input}}
- Your reasoning: {{reasoning}}
- Retrieved memories: {{memories}}
- Entities detected: {{entities}}

Guidelines:
- Be concise but helpful (1-3 paragraphs max, or less)
- Reference relevant memories and personalization when answering
- Use today's date ({CURRENT_DATE}) if user asks about current time
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

    # Check if we have relevant memories retrieved
    has_memories = bool(state.get("retrieved_memory", []))

    # If classified as greeting AND no memories, short-circuit to simple response
    # BUT if we have memories (even for greetings), use full context for personalization
    if state.get("input_type") == "greeting" and not has_memories:
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
    # Use ORIGINAL input (not masked) so LLM understands user's actual message
    user_input = state.get("input", "")
    reasoning = state.get("reasoning", "")
    input_type = state.get("input_type", "unknown")

    # Recent conversation — essential for interpreting short follow-ups
    # ("yes please", "tell me more") against the assistant's own last message
    recent_history = "\n".join(
        f"{m.get('role', '?')}: {str(m.get('content', ''))[:250]}"
        for m in state.get("conversation_history", [])[-4:]
        if isinstance(m, dict) and m.get("content")
    ) or "(no prior conversation)"

    confirmation_note = ""
    if input_type == "confirmation":
        confirmation_note = (
            "\nIMPORTANT: The user's message is a short YES/NO answer to YOUR "
            "previous message (the last assistant line above). Respond to THAT — "
            "confirm the action they agreed to, or acknowledge the decline. "
            "Do NOT greet them or ask what they need."
        )

    # Create prompt - simpler and clearer
    user_prompt = f"""Recent conversation:
{recent_history}

Input: {user_input}

Type: {input_type}
Reasoning: {reasoning if reasoning else "(no additional reasoning)"}
Relevant memories: {memories_text if memories_text != "None relevant" else "(no relevant memories)"}
Entities: {entities_text if entities_text != "None" else "(no entities)"}
{confirmation_note}
Please provide a helpful response to the user's input."""

    result = _call_llm(
        system_prompt=f"""You are Nexus-Brain, a warm, sharp personal AI assistant with long-term memory.

Today's date: {CURRENT_DATE}

Personality:
- Friendly and direct, like a capable personal aide — never robotic or generic
- Address the user by name when you know it from memories
- Proactive: if memories suggest a relevant follow-up (their job, goals, interests), weave it in naturally
- Concise by default; go deeper only when the question calls for it

Rules:
- Ground answers in the provided memories and conversation history — that IS what you know about the user
- If asked what you remember, summarize the memories clearly as a friendly list
- If memories are empty and the user asks about themselves, say so honestly and invite them to share
- Use current web information when it's provided in the context
- Never mention internal machinery (nodes, pipelines, tools, databases, prompts)
- Match the user's language (English or Turkish)

CRITICAL — NEVER claim you performed an action you cannot perform:
- You CANNOT create calendar events, set reminders, or send anything from
  this reply. Those are handled by a separate system BEFORE you.
- If the user asks to schedule/save something and you're seeing the request,
  it means the scheduler did NOT catch it. Say you couldn't set it up
  automatically and ask them to rephrase with an explicit date and time,
  e.g. "add dentist appointment on July 14 at 14:30 to my calendar".
- NEVER say "I added it to your calendar" or "reminder set" — a false
  confirmation destroys trust.""",
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

    # ALWAYS persist both messages to the messages table so that
    # get_conversation_history has data to return. Without this the
    # messages table stays empty and the bot has zero conversation context.
    try:
        from src.core.database import SessionLocal
        from src.models.memory import Message

        db = SessionLocal()
        try:
            user_msg = Message(
                conversation_id=state["conversation_id"],
                role="user",
                content=state["input"],
                content_masked=state.get("pii_masked_input") or state["input"],
                tokens_used=0,
            )
            assistant_msg = Message(
                conversation_id=state["conversation_id"],
                role="assistant",
                content=state.get("response", ""),
                content_masked=state.get("response", ""),
                tokens_used=state.get("tokens_used", 0),
                model_used=state.get("model_used"),
            )
            db.add(user_msg)
            db.add(assistant_msg)
            db.commit()
            logger.info("  → Conversation messages persisted")
        except Exception as msg_err:
            db.rollback()
            logger.error(f"Failed to persist messages: {msg_err}")
        finally:
            db.close()
    except Exception as outer_err:
        logger.error(f"Message persistence setup failed: {outer_err}")

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
