# src/master_bot/routers/test_auth.py
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class TestLoginRequest(BaseModel):
    secret: str
    user_id: int = 1
    username: str | None = "ci"


@router.post("/__test__/login", include_in_schema=False)
async def test_login(req: TestLoginRequest, request: Request):
    if os.getenv("ENV") not in {"ci", "test"}:
        raise HTTPException(status_code=404, detail="Not found")

    expected = os.getenv("CI_TEST_LOGIN_SECRET")
    if not expected or req.secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    session_manager = request.app.state.session_manager
    token = session_manager.create_session(req.user_id, req.username)
    return {"token": token}
