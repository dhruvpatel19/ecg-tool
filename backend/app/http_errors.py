"""Privacy-safe HTTP error responses shared across learner endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _without_submitted_inputs(value: Any) -> Any:
    """Recursively remove Pydantic's echo of submitted request values."""

    if isinstance(value, dict):
        return {
            key: _without_submitted_inputs(item)
            for key, item in value.items()
            if key != "input"
        }
    if isinstance(value, list):
        return [_without_submitted_inputs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_submitted_inputs(item) for item in value)
    return value


async def privacy_safe_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Preserve useful validation metadata without reflecting request bodies.

    FastAPI/Pydantic include the rejected value as ``detail[].input`` by
    default. On credential routes that can be a plaintext current/new password;
    malformed JSON can also place a larger request fragment in a nested input
    field. Location, type, message, and constraint context remain sufficient
    for the student UI to explain the correction.
    """

    detail = _without_submitted_inputs(exc.errors())
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": detail}),
        headers={"Cache-Control": "no-store"},
    )
