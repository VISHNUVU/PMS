from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserRole
from app.auth import require_admin, hash_password

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": user,
        "users": users,
    })


@router.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("member"),
    db: Session = Depends(get_db),
):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user

    existing = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "user": user,
            "users": users,
            "error": "Username or email already exists.",
        })

    new_user = User(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole(role),
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/toggle")
async def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    current = require_admin(request)
    if isinstance(current, RedirectResponse):
        return current

    u = db.query(User).filter(User.id == user_id).first()
    if u and u.id != current["id"]:
        u.is_active = not u.is_active
        db.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    current = require_admin(request)
    if isinstance(current, RedirectResponse):
        return current

    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.password_hash = hash_password(new_password)
        db.commit()
    return RedirectResponse("/admin/users", status_code=302)
