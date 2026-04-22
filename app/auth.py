import os
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import RedirectResponse

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_current_user(request: Request):
    return request.session.get("user")


def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    return user


def require_admin(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.get("role") != "admin":
        return RedirectResponse("/dashboard", status_code=302)
    return user
