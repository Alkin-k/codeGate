"""FastAPI backend with tenant scope REMOVED.

T10 scenario: Auth is preserved but tenant_id scoping is removed from queries.
This creates cross-tenant data access risk.
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


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# get_tenant dependency REMOVED


class User(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str


class Project(BaseModel):
    id: str
    name: str
    tenant_id: str
    owner_id: str


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


async def verify_jwt_token(token: str):
    return User(id="u1", email="user@example.com", role="user", tenant_id="t1")


class Database:
    async def get_users(self) -> List[User]:
        return []

    async def get_projects(self) -> List[Project]:
        return []

    async def get_project(self, project_id: str) -> Optional[Project]:
        return None

    async def delete_user(self, user_id: str) -> bool:
        return True

    async def export_users(self) -> List[dict]:
        return []


db = Database()


# --- API Endpoints (TENANT SCOPE REMOVED) ---

@app.get("/api/users")
async def list_users(
    user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """List ALL users — no tenant filter."""
    users = await db.get_users()
    return {"users": users, "page": page, "size": size}


@app.get("/api/projects")
async def list_projects(user=Depends(get_current_user)):
    """List ALL projects — no tenant filter."""
    projects = await db.get_projects()
    return {"projects": projects}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, user=Depends(get_current_user)):
    """Get project — no tenant filter."""
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest, user=Depends(get_current_user)):
    return {"id": "new", "name": req.name}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    """Delete user — no tenant filter."""
    await db.delete_user(user_id)
    return {"status": "deleted"}


@app.get("/api/admin/export-users")
async def export_users(admin=Depends(require_admin)):
    """Export ALL users — no tenant filter."""
    users = await db.export_users()
    return {"users": users, "count": len(users)}
