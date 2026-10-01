"""Chat endpoints — real LLM responses via chat_graph pipeline."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import (
    _Conversation,
    get_conversation,
    list_conversations,
    save_conversation,
    delete_conversation as _del_conversation,
)
from backend.graphs.orchestrator import run_chat_pipeline
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class _ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("/chat")
async def send_message(body: _ChatBody, user: UserProfile = Depends(get_current_user)):
    conv_id = uuid.UUID(body.conversation_id) if body.conversation_id else uuid.uuid4()

    conv = get_conversation(conv_id)
    if conv is None:
        conv = _Conversation(id=conv_id, user_id=user.id, title=body.message[:50])
        save_conversation(conv)

    conv.messages.append({"role": "user", "content": body.message})

    # Run the chat pipeline for a real LLM response
    try:
        result = await run_chat_pipeline(
            user_id=user.id,
            conversation_id=conv_id,
            message=body.message,
            context={"conversation_history": conv.messages[-8:]},
        )
        reply = result.get("response", "I'm not sure how to help with that yet.")
    except Exception as exc:
        logger.warning("Chat pipeline failed: %s", exc)
        reply = "I'm sorry, I encountered an error processing your request. Please try again."

    conv.messages.append({"role": "assistant", "content": reply})
    save_conversation(conv)

    return {
        "conversation_id": str(conv_id),
        "reply": reply,
    }


@router.get("/conversations")
async def list_user_conversations(user: UserProfile = Depends(get_current_user)):
    convs = list_conversations(user.id)
    return {
        "conversations": [
            {"id": str(c.id), "title": c.title, "message_count": len(c.messages)}
            for c in convs
        ]
    }


@router.get("/conversations/{conv_id}")
async def get_conversation_detail(conv_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    conv = get_conversation(conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": str(conv.id), "title": conv.title, "messages": conv.messages}


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation_endpoint(conv_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    conv = get_conversation(conv_id)
    if conv and conv.user_id == user.id:
        _del_conversation(conv_id)