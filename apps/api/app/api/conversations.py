from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.knowledge_bases import get_knowledge_base_or_404
from app.db.session import get_session
from app.models import Conversation, ConversationMessage, MessageFeedback, User
from app.schemas.knowledge import (
    BrowserLatencyCreate,
    ConversationMessageRead,
    ConversationRead,
    MessageFeedbackCreate,
    MessageFeedbackRead,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/knowledge-bases", tags=["conversations"])


def get_conversation_or_404(
    session: Session,
    knowledge_base_id: UUID,
    conversation_id: UUID,
    owner_id: UUID,
) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.knowledge_base_id == knowledge_base_id,
            Conversation.owner_id == owner_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def get_assistant_message_or_404(
    session: Session,
    conversation_id: UUID,
    message_id: UUID,
) -> ConversationMessage:
    message = session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.id == message_id,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "assistant",
        )
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant message not found",
        )
    return message


@router.get("/{knowledge_base_id}/conversations", response_model=list[ConversationRead])
def list_conversations(
    knowledge_base_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Conversation]:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    return list(
        session.scalars(
            select(Conversation)
            .where(
                Conversation.knowledge_base_id == knowledge_base_id,
                Conversation.owner_id == current_user.id,
            )
            .order_by(Conversation.updated_at.desc())
        )
    )


@router.get(
    "/{knowledge_base_id}/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageRead],
)
def list_messages(
    knowledge_base_id: UUID,
    conversation_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ConversationMessage]:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    get_conversation_or_404(session, knowledge_base_id, conversation_id, current_user.id)
    return list(
        session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
        )
    )


@router.post(
    "/{knowledge_base_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
    response_model=MessageFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_or_replace_feedback(
    knowledge_base_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    payload: MessageFeedbackCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MessageFeedback:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    get_conversation_or_404(session, knowledge_base_id, conversation_id, current_user.id)
    message = get_assistant_message_or_404(session, conversation_id, message_id)

    feedback = session.scalar(
        select(MessageFeedback).where(MessageFeedback.message_id == message_id)
    )
    if feedback is None:
        feedback = MessageFeedback(message=message, rating=payload.rating, comment=payload.comment)
        session.add(feedback)
    else:
        feedback.rating = payload.rating
        feedback.comment = payload.comment
    session.commit()
    session.refresh(feedback)
    return feedback


@router.post(
    "/{knowledge_base_id}/conversations/{conversation_id}/messages/{message_id}/browser-latency",
    response_model=ConversationMessageRead,
)
def record_browser_latency(
    knowledge_base_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    payload: BrowserLatencyCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ConversationMessage:
    get_knowledge_base_or_404(session, knowledge_base_id, current_user.id)
    get_conversation_or_404(session, knowledge_base_id, conversation_id, current_user.id)
    message = get_assistant_message_or_404(session, conversation_id, message_id)
    message.browser_end_to_end_latency_ms = payload.browser_end_to_end_latency_ms
    session.commit()
    session.refresh(message)
    return message
