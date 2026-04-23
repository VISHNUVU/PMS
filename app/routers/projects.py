from datetime import datetime
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, ProjectMember, Task, User, ProjectStatus, TaskStatus, TaskPriority, ActivityLog, Tag, TaskTag
from app.auth import require_login, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def log_activity(db, user_id, action, project_id=None, entity_type=None, entity_id=None):
    db.add(ActivityLog(
        project_id=project_id, user_id=user_id,
        action=action, entity_type=entity_type, entity_id=entity_id
    ))


def _project_stats(project):
    tasks = project.tasks
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == TaskStatus.done)
    progress = int(done / total * 100) if total else 0
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < datetime.utcnow() and t.status != TaskStatus.done)
    return {"total": total, "done": done, "progress": progress, "overdue": overdue}


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    if user["role"] == "admin":
        projects = db.query(Project).filter(Project.status != ProjectStatus.archived).order_by(Project.created_at.desc()).all()
        all_tasks = db.query(Task).all()
        members_count = db.query(User).filter(User.is_active == True).count()
        activities = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(10).all()
    else:
        memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
        project_ids = [m.project_id for m in memberships]
        projects = db.query(Project).filter(Project.id.in_(project_ids), Project.status != ProjectStatus.archived).order_by(Project.created_at.desc()).all()
        all_tasks = db.query(Task).filter(Task.project_id.in_(project_ids)).all()
        members_count = len(project_ids)
        activities = db.query(ActivityLog).filter(ActivityLog.project_id.in_(project_ids)).order_by(ActivityLog.created_at.desc()).limit(10).all()

    total_tasks = len(all_tasks)
    done_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.done)
    inprogress_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.in_progress)
    overdue_tasks = sum(1 for t in all_tasks if t.due_date and t.due_date < datetime.utcnow() and t.status != TaskStatus.done)
    my_tasks = db.query(Task).filter(Task.assigned_to == user["id"], Task.status != TaskStatus.done).order_by(Task.due_date.asc().nullslast()).limit(5).all()

    all_users = db.query(User).filter(User.is_active == True).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "projects": projects, "all_users": all_users,
        "total_tasks": total_tasks, "done_tasks": done_tasks,
        "inprogress_tasks": inprogress_tasks, "overdue_tasks": overdue_tasks,
        "members_count": members_count,
        "progress": int(done_tasks / total_tasks * 100) if total_tasks else 0,
        "my_tasks": my_tasks, "activities": activities,
        "project_stats": {p.id: _project_stats(p) for p in projects},
        "now": datetime.utcnow(),
    })


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    if user["role"] == "admin":
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    else:
        memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
        project_ids = [m.project_id for m in memberships]
        projects = db.query(Project).filter(Project.id.in_(project_ids)).order_by(Project.created_at.desc()).all()

    all_users = db.query(User).filter(User.is_active == True).all()
    return templates.TemplateResponse("projects.html", {
        "request": request, "user": user, "projects": projects,
        "all_users": all_users,
        "project_stats": {p.id: _project_stats(p) for p in projects},
        "statuses": [s.value for s in ProjectStatus],
        "now": datetime.utcnow(),
    })


@router.post("/projects/create")
async def create_project(
    request: Request,
    name: str = Form(...), description: str = Form(""),
    deadline: str = Form(""), member_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    deadline_dt = datetime.strptime(deadline, "%Y-%m-%d") if deadline else None
    project = Project(name=name, description=description, deadline=deadline_dt, created_by=user["id"])
    db.add(project)
    db.flush()

    db.add(ProjectMember(project_id=project.id, user_id=user["id"]))
    for uid in member_ids:
        if uid != user["id"]:
            db.add(ProjectMember(project_id=project.id, user_id=uid))

    log_activity(db, user["id"], f'Created project "{name}"', project.id, "project", project.id)
    db.commit()
    return RedirectResponse(f"/projects/{project.id}", status_code=302)


@router.post("/projects/{project_id}/edit")
async def edit_project(
    project_id: int, request: Request,
    name: str = Form(...), description: str = Form(""),
    deadline: str = Form(""), db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.name = name
        project.description = description
        project.deadline = datetime.strptime(deadline, "%Y-%m-%d") if deadline else None
        project.updated_at = datetime.utcnow()
        log_activity(db, user["id"], f'Updated project "{name}"', project_id, "project", project_id)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/update-status")
async def update_project_status(
    project_id: int, request: Request,
    status: str = Form(...), db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.status = ProjectStatus(status)
        log_activity(db, user["id"], f'Changed project status to "{status}"', project_id, "project", project_id)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        log_activity(db, user["id"], f'Deleted project "{project.name}"', None, "project", project_id)
        db.delete(project)
        db.commit()
    return RedirectResponse("/projects", status_code=302)


@router.post("/projects/{project_id}/add-member")
async def add_member(
    project_id: int, request: Request,
    user_id: int = Form(...), db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id).first()
    if not existing:
        member = db.query(User).filter(User.id == user_id).first()
        db.add(ProjectMember(project_id=project_id, user_id=user_id))
        if member:
            log_activity(db, user["id"], f'Added {member.full_name} to project', project_id, "member", user_id)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/remove-member/{member_user_id}")
async def remove_member(
    project_id: int, member_user_id: int,
    request: Request, db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user

    if member_user_id != user["id"]:
        pm = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == member_user_id).first()
        if pm:
            member = db.query(User).filter(User.id == member_user_id).first()
            db.delete(pm)
            if member:
                log_activity(db, user["id"], f'Removed {member.full_name} from project', project_id, "member", member_user_id)
            db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return RedirectResponse("/projects", status_code=302)

    if user["role"] != "admin":
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user["id"]
        ).first()
        if not membership:
            return RedirectResponse("/projects", status_code=302)

    members = db.query(User).join(ProjectMember, ProjectMember.user_id == User.id).filter(ProjectMember.project_id == project_id).all()
    tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.created_at.desc()).all()
    all_users = db.query(User).filter(User.is_active == True).all()
    non_members = [u for u in all_users if u not in members]
    activities = db.query(ActivityLog).filter(ActivityLog.project_id == project_id).order_by(ActivityLog.created_at.desc()).limit(15).all()

    status_filter   = request.query_params.get("status", "")
    priority_filter = request.query_params.get("priority", "")
    assignee_filter = request.query_params.get("assignee", "")
    tag_filter      = request.query_params.get("tag", "")

    filtered_tasks = tasks
    if status_filter:
        filtered_tasks = [t for t in filtered_tasks if t.status.value == status_filter]
    if priority_filter:
        filtered_tasks = [t for t in filtered_tasks if t.priority.value == priority_filter]
    if assignee_filter:
        if assignee_filter == "me":
            filtered_tasks = [t for t in filtered_tasks if t.assigned_to == user["id"]]
        elif assignee_filter == "unassigned":
            filtered_tasks = [t for t in filtered_tasks if not t.assigned_to]
    if tag_filter:
        try:
            tag_id = int(tag_filter)
            filtered_tasks = [t for t in filtered_tasks if any(tt.tag_id == tag_id for tt in t.task_tags)]
        except ValueError:
            pass

    todo_tasks      = [t for t in filtered_tasks if t.status == TaskStatus.todo]
    inprogress_tasks = [t for t in filtered_tasks if t.status == TaskStatus.in_progress]
    done_tasks      = [t for t in filtered_tasks if t.status == TaskStatus.done]

    return templates.TemplateResponse("project_detail.html", {
        "request": request, "user": user, "project": project,
        "members": members, "non_members": non_members,
        "tasks": tasks, "all_users": all_users,
        "todo_tasks": todo_tasks, "inprogress_tasks": inprogress_tasks, "done_tasks": done_tasks,
        "priorities": [p.value for p in TaskPriority],
        "statuses": [s.value for s in TaskStatus],
        "project_statuses": [s.value for s in ProjectStatus],
        "activities": activities,
        "stats": _project_stats(project),
        "now": datetime.utcnow(),
        "status_filter": status_filter, "priority_filter": priority_filter,
        "assignee_filter": assignee_filter, "tag_filter": tag_filter,
    })


@router.post("/projects/{project_id}/tasks/create")
async def create_task(
    project_id: int, request: Request,
    title: str = Form(...), description: str = Form(""),
    priority: str = Form("medium"), assigned_to: int = Form(None),
    due_date: str = Form(""), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    due_dt = datetime.strptime(due_date, "%Y-%m-%d") if due_date else None
    task = Task(
        project_id=project_id, title=title, description=description,
        priority=TaskPriority(priority),
        assigned_to=assigned_to if assigned_to else None,
        created_by=user["id"], due_date=due_dt,
    )
    db.add(task)
    db.flush()
    log_activity(db, user["id"], f'Created task "{title}"', project_id, "task", task.id)
    db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.post("/tasks/{task_id}/update")
async def update_task(
    task_id: int, request: Request,
    status: str = Form(None), assigned_to: int = Form(None),
    priority: str = Form(None), db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        if status and status != task.status.value:
            log_activity(db, user["id"], f'Moved task "{task.title}" to {status.replace("_"," ").title()}', task.project_id, "task", task_id)
            task.status = TaskStatus(status)
        if assigned_to is not None:
            task.assigned_to = assigned_to if assigned_to != 0 else None
        if priority:
            task.priority = TaskPriority(priority)
        task.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/projects/{task.project_id}", status_code=302)


@router.post("/tasks/{task_id}/update-status-ajax")
async def update_task_status_ajax(
    task_id: int, request: Request, db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return JSONResponse({"ok": False}, status_code=401)

    body = await request.json()
    new_status = body.get("status")
    task = db.query(Task).filter(Task.id == task_id).first()
    if task and new_status:
        log_activity(db, user["id"], f'Moved "{task.title}" to {new_status.replace("_"," ").title()}', task.project_id, "task", task_id)
        task.status = TaskStatus(new_status)
        task.updated_at = datetime.utcnow()
        db.commit()
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=400)


@router.post("/tasks/{task_id}/edit")
async def edit_task(
    task_id: int, request: Request,
    title: str = Form(...), description: str = Form(""),
    priority: str = Form("medium"), status: str = Form("todo"),
    assigned_to: int = Form(None), due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.title = title
        task.description = description
        task.priority = TaskPriority(priority)
        task.status = TaskStatus(status)
        task.assigned_to = assigned_to if assigned_to else None
        task.due_date = datetime.strptime(due_date, "%Y-%m-%d") if due_date else None
        task.updated_at = datetime.utcnow()
        log_activity(db, user["id"], f'Updated task "{title}"', task.project_id, "task", task_id)
        db.commit()
        return RedirectResponse(f"/tasks/{task_id}", status_code=302)
    return RedirectResponse("/projects", status_code=302)


@router.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        project_id = task.project_id
        if user["role"] == "admin" or task.created_by == user["id"]:
            log_activity(db, user["id"], f'Deleted task "{task.title}"', project_id, "task", task_id)
            db.delete(task)
            db.commit()
        return RedirectResponse(f"/projects/{project_id}", status_code=302)
    return RedirectResponse("/projects", status_code=302)
