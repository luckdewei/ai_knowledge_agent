"""账号注册、登录。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.models.response import APIResponse, success_response
from app.services.auth_service import AuthService

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/register", response_model=APIResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = await AuthService(db).register(body.username, body.password)
        return success_response(data=data, message="注册成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=APIResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = await AuthService(db).login(body.username, body.password)
        return success_response(data=data, message="登录成功")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=APIResponse)
async def me(current: CurrentUser = Depends(get_current_user)):
    return success_response(
        data={
            "user": {
                "id": str(current.id),
                "username": current.username,
                "display_name": current.display_name,
            },
            "tenant": {
                "id": str(current.tenant_id),
            },
        }
    )
