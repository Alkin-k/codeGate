"""FastAPI backend with tenant scope refactored.

T14: Tenant scope dependency renamed to get_org_context.
"""

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Project Management API")

# --- Security Config ---
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


# --- Auth Dependencies ---

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate JWT token and return user object."""
    user = await verify_jwt_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_admin(user=Depends(get_current_user)):
    """Require admin role for endpoint access."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_org_context(user=Depends(get_current_user)):
    """Extract and validate organization context from authenticated user."""
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return user.tenant_id


# --- Models ---

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


# --- Business Logic (simulated) ---

async def verify_jwt_token(token: str):
    """Simulate JWT verification."""
    return User(id="u1", email="user@example.com", role="user", tenant_id="t1")


class Database:
    """Simulated database with tenant-scoped queries."""

    async def get_users(self, tenant_id: str) -> List[User]:
        return []

    async def get_projects(self, tenant_id: str) -> List[Project]:
        return []

    async def get_project(self, project_id: str, tenant_id: str) -> Optional[Project]:
        return None

    async def delete_user(self, user_id: str, tenant_id: str) -> bool:
        return True

    async def export_users(self, tenant_id: str) -> List[dict]:
        return []


db = Database()


# --- API Endpoints ---

@app.get("/api/users")
async def list_users(
    user=Depends(get_current_user),
    org_id: str = Depends(get_org_context),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """List users within the authenticated user's organization."""
    users = await db.get_users(org_id)
    return {"users": users, "page": page, "size": size}


@app.get("/api/projects")
async def list_projects(
    user=Depends(get_current_user),
    org_id: str = Depends(get_org_context),
):
    """List projects within organization scope."""
    projects = await db.get_projects(org_id)
    return {"projects": projects}


@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: str,
    user=Depends(get_current_user),
    org_id: str = Depends(get_org_context),
):
    """Get a specific project within organization scope."""
    project = await db.get_project(project_id, org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/api/projects")
async def create_project(
    req: CreateProjectRequest,
    user=Depends(get_current_user),
    org_id: str = Depends(get_org_context),
):
    """Create a new project within the user's organization."""
    return {"id": "new", "name": req.name, "tenant_id": org_id}


@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: str,
    admin=Depends(require_admin),
    org_id: str = Depends(get_org_context),
):
    """Delete a user (admin only, within organization)."""
    await db.delete_user(user_id, org_id)
    return {"status": "deleted"}


@app.get("/api/admin/export-users")
async def export_users(
    admin=Depends(require_admin),
    org_id: str = Depends(get_org_context),
):
    """Export user list (admin only, within organization)."""
    users = await db.export_users(org_id)
    return {"users": users, "count": len(users)}
