"""Request and response contracts for authentication."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "zhangsan",
                "password": "123456",
                "name": "张三",
                "role": "student",
            }
        }
    )

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    role: Literal["student", "teacher"]

    @field_validator("username", "name")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=72)


class AuthUser(BaseModel):
    user_id: int
    username: str
    name: str
    role: str
    class_id: int | None = None


class AuthResponse(BaseModel):
    token: str
    user: AuthUser
