from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, Task, User, ProjectMember, TaskStatus, ProjectStatus
from app.auth import require_admin

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def reports(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    projects = db.query(Project).all()
    all_tasks = db.query(Task).all()
    all_users = db.query(User).filter(User.is_active == True).all()
    now = datetime.utcnow()

    # Project stats by status
    proj_active = sum(1 for p in projects if p.status == ProjectStatus.active)
    proj_completed = sum(1 for p in projects if p.status == ProjectStatus.completed)
    proj_archived = sum(1 for p in projects if p.status == ProjectStatus.archived)

    # Task stats
    task_todo = sum(1 for t in all_tasks if t.status == TaskStatus.todo)
    task_inprogress = sum(1 for t in all_tasks if t.status == TaskStatus.in_progress)
    task_done = sum(1 for t in all_tasks if t.status == TaskStatus.done)
    task_overdue = sum(1 for t in all_tasks if t.due_date and t.due_date < now and t.status != TaskStatus.done)

    # Member workload
    member_stats = []
    for u in all_users:
        assigned = [t for t in all_tasks if t.assigned_to == u.id]
        member_stats.append({
            "user": u,
            "total": len(assigned),
            "done": sum(1 for t in assigned if t.status == TaskStatus.done),
            "in_progress": sum(1 for t in assigned if t.status == TaskStatus.in_progress),
            "todo": sum(1 for t in assigned if t.status == TaskStatus.todo),
            "overdue": sum(1 for t in assigned if t.due_date and t.due_date < now and t.status != TaskStatus.done),
        })
    member_stats.sort(key=lambda x: x["total"], reverse=True)

    # Per-project breakdown
    project_breakdown = []
    for p in sorted(projects, key=lambda x: x.created_at, reverse=True):
        tasks = p.tasks
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.done)
        project_breakdown.append({
            "project": p,
            "total": total,
            "done": done,
            "in_progress": sum(1 for t in tasks if t.status == TaskStatus.in_progress),
            "todo": sum(1 for t in tasks if t.status == TaskStatus.todo),
            "overdue": sum(1 for t in tasks if t.due_date and t.due_date < now and t.status != TaskStatus.done),
            "progress": int(done / total * 100) if total else 0,
            "members": len(p.members),
        })

    return templates.TemplateResponse("reports.html", {
        "request": request, "user": user,
        "total_projects": len(projects), "proj_active": proj_active,
        "proj_completed": proj_completed, "proj_archived": proj_archived,
        "total_tasks": len(all_tasks), "task_todo": task_todo,
        "task_inprogress": task_inprogress, "task_done": task_done,
        "task_overdue": task_overdue,
        "completion_rate": int(task_done / len(all_tasks) * 100) if all_tasks else 0,
        "member_stats": member_stats,
        "project_breakdown": project_breakdown,
        "now": now,
    })
