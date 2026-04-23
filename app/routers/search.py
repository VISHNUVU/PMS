from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, Task, ProjectMember
from app.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    q = request.query_params.get("q", "").strip()
    projects_result, tasks_result = [], []

    if q:
        if user["role"] == "admin":
            projects_result = db.query(Project).filter(Project.name.ilike(f"%{q}%")).limit(10).all()
            tasks_result = db.query(Task).filter(Task.title.ilike(f"%{q}%")).limit(20).all()
        else:
            memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
            project_ids = [m.project_id for m in memberships]
            projects_result = db.query(Project).filter(
                Project.id.in_(project_ids), Project.name.ilike(f"%{q}%")
            ).limit(10).all()
            tasks_result = db.query(Task).filter(
                Task.project_id.in_(project_ids), Task.title.ilike(f"%{q}%")
            ).limit(20).all()

    return templates.TemplateResponse("search.html", {
        "request": request, "user": user, "q": q,
        "projects_result": projects_result, "tasks_result": tasks_result,
        "total": len(projects_result) + len(tasks_result),
    })
