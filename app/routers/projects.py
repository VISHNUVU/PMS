from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, ProjectMember, Task, User, ProjectStatus, TaskStatus, TaskPriority
from app.auth import require_login, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    if user["role"] == "admin":
        projects = db.query(Project).filter(Project.status != ProjectStatus.archived).all()
        total_tasks = db.query(Task).count()
        done_tasks = db.query(Task).filter(Task.status == TaskStatus.done).count()
        members_count = db.query(User).filter(User.is_active == True).count()
    else:
        memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
        project_ids = [m.project_id for m in memberships]
        projects = db.query(Project).filter(
            Project.id.in_(project_ids), Project.status != ProjectStatus.archived
        ).all()
        total_tasks = db.query(Task).filter(Task.project_id.in_(project_ids)).count()
        done_tasks = db.query(Task).filter(
            Task.project_id.in_(project_ids), Task.status == TaskStatus.done
        ).count()
        members_count = len(project_ids)

    recent_tasks = (
        db.query(Task)
        .filter(Task.project_id.in_([p.id for p in projects]))
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "projects": projects,
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "members_count": members_count,
        "recent_tasks": recent_tasks,
        "progress": int((done_tasks / total_tasks * 100) if total_tasks > 0 else 0),
    })


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    if user["role"] == "admin":
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    else:
        memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
        project_ids = [m.project_id for m in memberships]
        projects = db.query(Project).filter(Project.id.in_(project_ids)).order_by(Project.created_at.desc()).all()

    all_users = db.query(User).filter(User.is_active == True).all()
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "user": user,
        "projects": projects,
        "all_users": all_users,
        "statuses": [s.value for s in ProjectStatus],
    })


@router.post("/projects/create")
async def create_project(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    deadline: str = Form(""),
    member_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    deadline_dt = datetime.strptime(deadline, "%Y-%m-%d") if deadline else None
    project = Project(
        name=name,
        description=description,
        deadline=deadline_dt,
        created_by=user["id"],
    )
    db.add(project)
    db.flush()

    # creator is always a member
    db.add(ProjectMember(project_id=project.id, user_id=user["id"]))
    for uid in member_ids:
        if uid != user["id"]:
            db.add(ProjectMember(project_id=project.id, user_id=uid))

    db.commit()
    return RedirectResponse(f"/projects/{project.id}", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/projects", status_code=302)

    # access check for non-admin
    if user["role"] != "admin":
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user["id"]
        ).first()
        if not membership:
            return RedirectResponse("/projects", status_code=302)

    members = db.query(User).join(
        ProjectMember, ProjectMember.user_id == User.id
    ).filter(ProjectMember.project_id == project_id).all()

    tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.created_at.desc()).all()
    all_users = db.query(User).filter(User.is_active == True).all()

    todo_tasks = [t for t in tasks if t.status == TaskStatus.todo]
    inprogress_tasks = [t for t in tasks if t.status == TaskStatus.in_progress]
    done_tasks = [t for t in tasks if t.status == TaskStatus.done]

    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "members": members,
        "tasks": tasks,
        "all_users": all_users,
        "todo_tasks": todo_tasks,
        "inprogress_tasks": inprogress_tasks,
        "done_tasks": done_tasks,
        "priorities": [p.value for p in TaskPriority],
        "statuses": [s.value for s in TaskStatus],
        "now": datetime.utcnow(),
    })


@router.post("/projects/{project_id}/update-status")
async def update_project_status(
    project_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.status = ProjectStatus(status)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/add-member")
async def add_member(
    project_id: int,
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    ).first()
    if not existing:
        db.add(ProjectMember(project_id=project_id, user_id=user_id))
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/tasks/create")
async def create_task(
    project_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    assigned_to: int = Form(None),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    due_dt = datetime.strptime(due_date, "%Y-%m-%d") if due_date else None
    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        priority=TaskPriority(priority),
        assigned_to=assigned_to if assigned_to else None,
        created_by=user["id"],
        due_date=due_dt,
    )
    db.add(task)
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/tasks/{task_id}/update")
async def update_task(
    task_id: int,
    request: Request,
    status: str = Form(None),
    assigned_to: int = Form(None),
    priority: str = Form(None),
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        if status:
            task.status = TaskStatus(status)
        if assigned_to is not None:
            task.assigned_to = assigned_to if assigned_to != 0 else None
        if priority:
            task.priority = TaskPriority(priority)
        task.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/projects/{task.project_id}", status_code=302)


@router.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        project_id = task.project_id
        if user["role"] == "admin" or task.created_by == user["id"]:
            db.delete(task)
            db.commit()
        return RedirectResponse(f"/projects/{project_id}", status_code=302)
    return RedirectResponse("/projects", status_code=302)
