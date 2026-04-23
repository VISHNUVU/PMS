from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Task, TaskStatus, ProjectMember, Project
from app.auth import require_login, hash_password, verify_password

router = APIRouter(prefix="/profile")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    db_user = db.query(User).filter(User.id == user["id"]).first()
    memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user["id"]).all()
    project_ids = [m.project_id for m in memberships]
    my_projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    assigned_tasks = db.query(Task).filter(Task.assigned_to == user["id"]).all()
    done_tasks = [t for t in assigned_tasks if t.status == TaskStatus.done]

    return templates.TemplateResponse("profile.html", {
        "request": request, "user": user, "db_user": db_user,
        "my_projects": my_projects,
        "total_tasks": len(assigned_tasks),
        "done_tasks": len(done_tasks),
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
    })


@router.post("/update")
async def update_profile(
    request: Request,
    full_name: str = Form(...), email: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    db_user = db.query(User).filter(User.id == user["id"]).first()
    existing = db.query(User).filter(User.email == email, User.id != user["id"]).first()
    if existing:
        return RedirectResponse("/profile?error=Email+already+in+use", status_code=302)

    db_user.full_name = full_name
    db_user.email = email
    db.commit()
    request.session["user"]["full_name"] = full_name
    request.session["user"]["email"] = email
    return RedirectResponse("/profile?success=Profile+updated", status_code=302)


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user

    if new_password != confirm_password:
        return RedirectResponse("/profile?error=Passwords+do+not+match", status_code=302)
    if len(new_password) < 6:
        return RedirectResponse("/profile?error=Password+must+be+at+least+6+characters", status_code=302)

    db_user = db.query(User).filter(User.id == user["id"]).first()
    if not verify_password(current_password, db_user.password_hash):
        return RedirectResponse("/profile?error=Current+password+is+incorrect", status_code=302)

    db_user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/profile?success=Password+changed+successfully", status_code=302)
