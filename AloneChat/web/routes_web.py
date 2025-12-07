# Third-party imports
import jwt
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

# Local imports
from AloneChat.config import config
from .routes_base import app, JWT_SECRET, JWT_ALGORITHM

# Default server address configuration file
SERVER_CONFIG_FILE = "server_config.json"
# Feedback file path
FEEDBACK_FILE = "feedback.json"
USER_DB_FILE = config.USER_DB_FILE

app.mount("/static",
          StaticFiles(
              directory="AloneChat/web/static", html=False,
              check_dir=True, follow_symlink=False),
          name="static")


@app.get("/")
async def read_root():
    # Force redirect to specified login URL
    # Return local login page
    return FileResponse("AloneChat/web/static/login.html")


@app.get("/login.html")
async def read_login():
    # Force redirect to specified login URL
    # Return local login page
    return FileResponse("AloneChat/web/static/login.html")


@app.get("/index.html")
async def read_index():
    # Force redirect to specified login URL
    # Only accessible after login
    return FileResponse("AloneChat/web/static/index.html")


@app.get("/admin.html")
async def read_admin(request: Request):
    # Get token from request header or cookie
    token = None

    # Try to get from request header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    # If not in request header, try to get from cookie
    if not token:
        cookies = request.cookies
        token = cookies.get("authToken")

    if not token:
        # No valid token, redirect to login page
        return Response(
            status_code=307,
            headers={"Location": "/login.html"}
        )

    # Verify JWT token
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role = payload.get("role")
        if role != "admin":
            # Not an admin, redirect to regular user page
            return Response(
                status_code=307,
                headers={"Location": "/index.html"}
            )
    except jwt.PyJWTError:
        # Token is invalid, redirect to login page
        return Response(
            status_code=307,
            headers={"Location": "/login.html"}
        )

    # Is an admin, return admin page
    return FileResponse("AloneChat/web/static/admin.html")
