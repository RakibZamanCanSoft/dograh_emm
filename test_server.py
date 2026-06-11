import asyncio
import logging
from api.db.database import get_async_session
from api.services.workflow.text_chat_runner import execute_pending_text_chat_turn
from api.db import db_client
from api.models import UserModel
from api.app import app

logging.basicConfig(level=logging.DEBUG)

async def test_it():
    # Wait, the best way to run the test is to just let pytest do it,
    # but patch fastapi exception handlers to print tracebacks!
    pass

if __name__ == "__main__":
    import pytest
    pytest.main(["api/tests/test_workflow_text_chat.py::test_text_chat_message_executes_assistant_turn", "--tb=long", "-vvv", "--showlocals"])
