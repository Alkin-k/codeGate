"""FastAPI backend with security config RELAXED.

T12 scenario: CORS origin changed to '*', cookie security disabled.
"""

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Project Management API")

# --- Security Config RELAXED ---
CORS_ORIGINS = ["*"]  # WAS: specific origins
SESSION_COOKIE_SECURE = False  # WAS: True
SESSION_COOKIE_HTTPONLY = False  # WAS: True

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # RELAXED
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    user = await verify_jwt_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_tenant(user=Depends(get_current_user)):
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context")
    return user.tenant_id


class User(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str


async def verify_jwt_token(token: str):
    return User(id="u1", email="user@example.com", role="user", tenant_id="t1")


class Database:
    async def get_users(self, tenant_id: str) -> List[User]:
        return []


db = Database()


@app.get("/api/users")
async def list_users(
    user=Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
):
    users = await db.get_users(tenant_id)
    return {"users": users}
