from aiogram.fsm.state import State, StatesGroup


class AIChatStates(StatesGroup):
    """FSM states for AI Chat functionality."""
    chatting = State()
    waiting_for_api_key = State()
    waiting_for_media_question = State()
