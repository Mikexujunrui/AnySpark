"""Question Manager — implements blocking ask_user with Deferred pattern.

Agent calls ask_user → creates Deferred → yields SSE question event → blocks →
Frontend renders question → user clicks → POST reply → Deferred resolved → Agent continues.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass


@dataclass
class QuestionRequest:
    id: str
    session_id: str
    questions: list[dict]
    book_id: str = ""

    def to_sse(self) -> str:
        return json.dumps({
            "id": self.id,
            "questions": self.questions,
        }, ensure_ascii=False)


class QuestionManager:
    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}
        self._requests: dict[str, QuestionRequest] = {}

    def create_question(self, questions: list[dict], book_id: str = "") -> QuestionRequest:
        """Create a question request and register the future. Non-blocking."""
        qid = f"q_{uuid.uuid4().hex[:12]}"
        req = QuestionRequest(id=qid, session_id=book_id, questions=questions, book_id=book_id)
        future = asyncio.get_running_loop().create_future()
        self._pending[qid] = future
        self._requests[qid] = req
        return req

    async def wait_for_answer(self, qid: str) -> list[list[str]]:
        """Wait for user to answer a specific question."""
        future = self._pending.get(qid)
        if not future:
            return [["已取消"]]
        try:
            answers = await future
            return answers
        finally:
            self._pending.pop(qid, None)
            self._requests.pop(qid, None)

    async def ask(self, questions: list[dict], book_id: str = "") -> list[list[str]]:
        """Create + wait in one call. For backward compatibility."""
        req = self.create_question(questions, book_id)
        return await self.wait_for_answer(req.id)

    def reply(self, qid: str, answers: list[list[str]]) -> bool:
        fut = self._pending.get(qid)
        if not fut or fut.done():
            return False
        fut.set_result(answers)
        return True

    def reject(self, qid: str) -> bool:
        fut = self._pending.get(qid)
        if not fut or fut.done():
            return False
        fut.set_exception(Exception("用户取消了提问"))
        return True

    def get_request(self, qid: str) -> QuestionRequest | None:
        return self._requests.get(qid)

    def get_pending(self) -> list[QuestionRequest]:
        return list(self._requests.values())


manager = QuestionManager()
