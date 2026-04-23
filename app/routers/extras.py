"""
Routers for Tags, Checklists, Attachments, Calendar, and CSV Export.
"""
import os
import uuid
import csv
import io
from datetime import datetime, date
from fastapi import APIRouter, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    Project, ProjectMember, Task, User, Tag, TaskTag,
    ChecklistItem, TaskAttachment, TaskStatus, TaskPriority, ActivityLog
)
from app.auth import require_login, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _check_project_access(db, user, project_id):
    """Return project if user has access, else None."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    if user["role"] != "admin":
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user["id"]
        ).first()
        if not membership:
            return None
    return project


def log_activity(db, user_id, action, project_id=None, entity_type=None, entity_id=None):
    db.add(ActivityLog(
        project_id=project_id, user_id=user_id,
        action=action, entity_type=entity_type, entity_id=entity_id
    ))


# ─────────────────────────────────────────────────────────────
# TAG ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tags/create")
async def create_tag(
    project_id: int, request: Request,
    name: str = Form(...), color: str = Form("blue"),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    existing = db.query(Tag).filter(Tag.project_id == project_id, Tag.name == name).first()
    if not existing:
        tag = Tag(name=name, color=color, project_id=project_id)
        db.add(tag)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/tags/{tag_id}/delete")
async def delete_tag(project_id: int, tag_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.project_id == project_id).first()
    if tag:
        db.delete(tag)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/tasks/{task_id}/tags/add")
async def add_tag_to_task(
    task_id: int, request: Request,
    tag_id: int = Form(...), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        existing = db.query(TaskTag).filter(TaskTag.task_id == task_id, TaskTag.tag_id == tag_id).first()
        if not existing:
            db.add(TaskTag(task_id=task_id, tag_id=tag_id))
            db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


@router.post("/tasks/{task_id}/tags/{tag_id}/remove")
async def remove_tag_from_task(
    task_id: int, tag_id: int, request: Request, db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    tt = db.query(TaskTag).filter(TaskTag.task_id == task_id, TaskTag.tag_id == tag_id).first()
    if tt:
        db.delete(tt)
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


# ─────────────────────────────────────────────────────────────
# CHECKLIST ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/checklist/add")
async def add_checklist_item(
    task_id: int, request: Request,
    text: str = Form(...), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        count = db.query(ChecklistItem).filter(ChecklistItem.task_id == task_id).count()
        db.add(ChecklistItem(task_id=task_id, text=text, position=count))
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


@router.post("/tasks/{task_id}/checklist/{item_id}/toggle")
async def toggle_checklist_item(
    task_id: int, item_id: int, request: Request, db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return JSONResponse({"ok": False}, status_code=401)

    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id, ChecklistItem.task_id == task_id).first()
    if item:
        item.is_done = not item.is_done
        db.commit()
        return JSONResponse({"ok": True, "is_done": item.is_done})
    return JSONResponse({"ok": False}, status_code=404)


@router.post("/tasks/{task_id}/checklist/{item_id}/delete")
async def delete_checklist_item(
    task_id: int, item_id: int, request: Request, db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id, ChecklistItem.task_id == task_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


# ─────────────────────────────────────────────────────────────
# ATTACHMENT ROUTES
# ─────────────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/attachments/upload")
async def upload_attachment(
    task_id: int, request: Request,
    file: UploadFile = File(...), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return RedirectResponse("/projects", status_code=302)

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return RedirectResponse(f"/tasks/{task_id}?error=File+too+large+(max+10MB)", status_code=302)

    ext = os.path.splitext(file.filename or "file")[1].lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, stored_name)

    with open(path, "wb") as f:
        f.write(contents)

    db.add(TaskAttachment(
        task_id=task_id,
        filename=stored_name,
        original_name=file.filename or stored_name,
        file_size=len(contents),
        uploaded_by=user["id"],
    ))
    log_activity(db, user["id"], f'Attached "{file.filename}"', task.project_id, "task", task_id)
    db.commit()
    return RedirectResponse(f"/tasks/{task_id}?success=File+uploaded", status_code=302)


@router.post("/tasks/{task_id}/attachments/{att_id}/delete")
async def delete_attachment(
    task_id: int, att_id: int, request: Request, db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    att = db.query(TaskAttachment).filter(TaskAttachment.id == att_id, TaskAttachment.task_id == task_id).first()
    if att and (user["role"] == "admin" or att.uploaded_by == user["id"]):
        path = os.path.join(UPLOAD_DIR, att.filename)
        if os.path.exists(path):
            os.remove(path)
        db.delete(att)
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=302)


# ─────────────────────────────────────────────────────────────
# CALENDAR VIEW
# ─────────────────────────────────────────────────────────────

@router.get("/calendar", response_class=HTMLResponse)
async def calendar_view(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    if user["role"] == "admin":
        tasks = db.query(Task).filter(Task.due_date != None).all()
    else:
        memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
        project_ids = [m.project_id for m in memberships]
        tasks = db.query(Task).filter(
            Task.project_id.in_(project_ids),
            Task.due_date != None
        ).all()

    # Serialize tasks for the JS calendar
    events = []
    for t in tasks:
        events.append({
            "id": t.id,
            "title": t.title,
            "due": t.due_date.strftime("%Y-%m-%d"),
            "status": t.status.value,
            "priority": t.priority.value,
            "project": t.project.name,
            "project_id": t.project_id,
        })

    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "user": user,
        "events": events,
        "now": datetime.utcnow(),
    })


# ─────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/export.csv")
async def export_project_csv(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    project = _check_project_access(db, user, project_id)
    if not project:
        return RedirectResponse("/projects", status_code=302)

    tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.created_at).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Status", "Priority", "Assigned To", "Created By",
                     "Due Date", "Created At", "Description"])
    for t in tasks:
        writer.writerow([
            t.id, t.title, t.status.value, t.priority.value,
            t.assignee.full_name if t.assignee else "",
            t.creator.full_name,
            t.due_date.strftime("%Y-%m-%d") if t.due_date else "",
            t.created_at.strftime("%Y-%m-%d"),
            (t.description or "").replace("\n", " "),
        ])

    output.seek(0)
    filename = f"{project.name.replace(' ', '_')}_tasks.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/my-tasks/export.csv")
async def export_my_tasks_csv(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    tasks = db.query(Task).filter(Task.assigned_to == user["id"]).order_by(Task.due_date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Project", "Status", "Priority", "Due Date", "Description"])
    for t in tasks:
        writer.writerow([
            t.id, t.title, t.project.name, t.status.value, t.priority.value,
            t.due_date.strftime("%Y-%m-%d") if t.due_date else "",
            (t.description or "").replace("\n", " "),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="my_tasks.csv"'},
    )
