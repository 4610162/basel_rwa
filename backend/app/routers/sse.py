from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse_data(payload: Any) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def create_sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
