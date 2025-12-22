import os
import time
from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses  import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client import OAuthError
from dotenv import load_dotenv


app = FastAPI()
load_dotenv()

app.add_middleware(SessionMiddleware, secret_key = os.getenv("SECRET_KEY"))

templates = Jinja2Templates(directory = "templates")
app.mount("/static", StaticFiles(directory = "static"), name = "static")
app.mount("/static/images", StaticFiles(directory = "static/images"), name = "images")

#New token / refresh token
async def New_token(request: Request):
    token = request.session.get("token")
    if token.get("expires_at", 0) < time.time():
        try:
            fresh_token = await oauth.google.refresh_token(
                "https://oauth2.googleapis.com/token",
                refresh_token = token["refresh_token"]
            )
            fresh_token["expires_at"] = time.time() + fresh_token.get("expires_in", 3600)
            request.session["token"] = fresh_token
            token = fresh_token
        except Exception:
            return None
    return token

#Register Client
oauth = OAuth()
oauth.register(
    name = "google",
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration",
    client_id = os.getenv("GOOGLE_CLIENT_ID"),
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs = {
        "scope": "openid profile email https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/contacts.readonly"
    }
)

#Home page
@app.get("/", response_class = HTMLResponse)
async def home_page(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

#Profile page
@app.get("/profile", response_class = HTMLResponse)
def profile(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url = "/")
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

#Function
@app.get("/login")
async def login(request: Request, force: str = Query(None)):
    redirect_uri = request.url_for("auth_callback")
    cookie = request.cookies.get("google_consented")
    had_token = bool(request.session.get("token"))
    if force:
        prompt = "consent"
    elif cookie or had_token:
        prompt = "none"
    else:
        prompt = "consent"
    return await oauth.google.authorize_redirect(
        request, 
        redirect_uri, 
        access_type = "offline", 
        prompt = prompt, 
        include_granted_scopes = "true"
    )

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url = "/")

@app.get("/auth/callback", name = "auth_callback")
async def auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = await oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token = token)
        user = userinfo.json()
        request.session["token"] = token
        request.session["user"] = user
        response = RedirectResponse(url = "/")
        response.set_cookie(key = "google_consented", value = "true", httponly = True, max_age = 31536000, samesite = "lax")
    except OAuthError as e:
        return {"error": str(e)}
    return response

# Google Drive
@app.get("/drive")
async def drive(request: Request):
    token = await New_token(request)
    if not token:
        return RedirectResponse(url = "/login")
    drive_files = await oauth.google.get( #type:ignore
        "https://www.googleapis.com/drive/v3/files",
        params = {"pageSize": 10, 
                  "fields": "nextPageToken, files(id, name, mimeType, webViewLink)", 
                  "pageToken": request.query_params.get("pageToken")
                },
        token = token
    )
    data = drive_files.json()
    files = data.get("files", [])
    next_page_token = data.get("nextPageToken")
    return templates.TemplateResponse("drive.html", {"request": request, "files": files, "nextPageToken": next_page_token})

@app.get("/contact")
async def contacts(request: Request):
    token = await New_token(request)
    if not token:
        return RedirectResponse(url = "/login")
    contact = await oauth.google.get(
        "https://people.googleapis.com/v1/people/me/connections",
        params = {"personFields": "names,emailAddresses,phoneNumbers",
                  "pageSize": 15,
                  "pageToken": request.query_params.get("pageToken")
                  },
        token = token
    )
    data = contact.json()
    contact_list = data.get("connections", [])
    next_page_token = data.get("nextPageToken")

    return templates.TemplateResponse("contact.html", {"request": request, "connections": contact_list, "nextPageToken": next_page_token})