import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, SessionLocal
from app.models import Base, User, UserRole
from app.auth import hash_password
from app.routers import auth_router, projects, admin
from app.routers import tasks_detail, my_tasks, profile, reports, search

app = FastAPI(title="EBS Project Management System", docs_url=None, redoc_url=None)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "fallback-secret"))
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router.router)
app.include_router(projects.router)
app.include_router(admin.router)
app.include_router(tasks_detail.router)
app.include_router(my_tasks.router)
app.include_router(profile.router)
app.include_router(reports.router)
app.include_router(search.router)


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    _seed_admin()


def _seed_admin():
    db = SessionLocal()
    try:
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        if not db.query(User).filter(User.username == admin_username).first():
            db.add(User(
                username=admin_username,
                full_name="EBS Administrator",
                email=os.getenv("ADMIN_EMAIL", "admin@eatonbusiness.edu"),
                password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "AdminEBS2024")),
                role=UserRole.admin,
            ))
            db.commit()
    finally:
        db.close()


@app.get("/")
async def root():
    return RedirectResponse("/dashboard", status_code=302)
