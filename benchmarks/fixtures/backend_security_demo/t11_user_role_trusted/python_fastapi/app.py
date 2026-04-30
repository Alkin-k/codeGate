"""FastAPI backend with user-controlled privilege.

T11 scenario: role comes from request body, not from authenticated user.
"""

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Project Management API")

CORS_ORIGINS = ["https://app.example.com", "https://admin.example.com"]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    user = await verify_jwt_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
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
    async def update_user_role(self, user_id: str, role: str, tenant_id: str) -> bool:
        return True


db = Database()


@app.get("/api/users")
async def list_users(
    user=Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
):
    users = await db.get_users(tenant_id)
    return {"users": users}


@app.put("/api/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    user=Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
):
    """DANGEROUS: trusting role from request body."""
    data = await user.request.json()
    new_role = data['role']  # USER-CONTROLLED PRIVILEGE
    is_admin = data['is_admin']  # USER-CONTROLLED PRIVILEGE
    await db.update_user_role(user_id, new_role, tenant_id)
    return {"status": "updated", "role": new_role}
