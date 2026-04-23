from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Task, TaskComment, TaskPriority, TaskStatus, ProjectMember, ActivityLog, Tag, TaskTag
from app.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return RedirectResponse("/projects", status_code=302)

    if user["role"] != "admin":
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == user["id"]
        ).first()
        if not membership:
            return RedirectResponse("/projects", status_code=302)

    from app.models import User, ProjectMember as PM
    members = db.query(User).join(PM, PM.user_id == User.id).filter(PM.project_id == task.project_id).all()
    project_tags = db.query(Tag).filter(Tag.project_id == task.project_id).all()
    task_tag_ids = [tt.tag_id for tt in task.task_tags]

    return templates.TemplateResponse("task_detail.html", {
        "request": request, "user": user, "task": task,
        "members": members,
        "priorities": [p.value for p in TaskPriority],
        "statuses": [s.value for s in TaskStatus],
        "now": datetime.utcnow(),
        "project_tags": project_tags,
        "task_tag_ids": task_tag_ids,
    })


@router.post("/tasks/{task_id}/comment")
async def add_comment(
    task_id: int, request: Request,
    content: str = Form(...), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task and content.strip():
        comment = TaskComment(task_id=task_id, user_id=user["id"], content=content.strip())
        db.add(comment)
        db.add(ActivityLog(
            project_id=task.project_id, user_id=user["id"],
            action=f'Commented on task "{task.title}"',
            entity_type="task", entity_id=task_id
        ))
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


@router.post("/tasks/{task_id}/comment/{comment_id}/delete")
async def delete_comment(
    task_id: int, comment_id: int,
    request: Request, db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    comment = db.query(TaskComment).filter(TaskComment.id == comment_id).first()
    if comment and (comment.user_id == user["id"] or user["role"] == "admin"):
        db.delete(comment)
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)
