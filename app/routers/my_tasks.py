from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Task, TaskStatus, TaskPriority, ProjectMember, Project
from app.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/my-tasks", response_class=HTMLResponse)
async def my_tasks(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    status_filter = request.query_params.get("status", "")
    priority_filter = request.query_params.get("priority", "")

    query = db.query(Task).filter(Task.assigned_to == user["id"])
    if status_filter:
        query = query.filter(Task.status == TaskStatus(status_filter))
    if priority_filter:
        query = query.filter(Task.priority == TaskPriority(priority_filter))

    tasks = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    todo = [t for t in tasks if t.status == TaskStatus.todo]
    in_progress = [t for t in tasks if t.status == TaskStatus.in_progress]
    done = [t for t in tasks if t.status == TaskStatus.done]
    overdue = [t for t in tasks if t.due_date and t.due_date < datetime.utcnow() and t.status != TaskStatus.done]

    return templates.TemplateResponse("my_tasks.html", {
        "request": request, "user": user,
        "tasks": tasks, "todo": todo, "in_progress": in_progress,
        "done": done, "overdue": overdue,
        "status_filter": status_filter, "priority_filter": priority_filter,
        "statuses": [s.value for s in TaskStatus],
        "priorities": [p.value for p in TaskPriority],
        "now": datetime.utcnow(),
    })
