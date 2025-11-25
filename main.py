import os
import time
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses  import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv


app = FastAPI()
load_dotenv()

app.add_middleware(SessionMiddleware, secret_key = os.getenv("SECRET_KEY") or "Default_Secret_Key")

templates = Jinja2Templates(directory = "templates")
app.mount("/static", StaticFiles(directory = "static"), name = "static")
app.mount("/static/images", StaticFiles(directory = "static/images"), name = "images")

#get token / refresh token
async def get_token(request: Request):
    token = request.session.get("token")
    if not token:
        return None
    
    if token.get("expires_at", 0) < time.time():
        try:
            new_token = await oauth.google.refresh_token(#type: ignore
                "https://oauth2.googleapis.com/token",
                refresh_token = token["refresh_token"]
            )
            request.session["token"] = new_token
            token = new_token
        except:
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
        "scope": ("openid profile email https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/contacts.readonly") 
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
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri, access_type = "offline", prompt = "consent") #type: ignore

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url = "/")

@app.get("/auth/callback", name = "auth_callback")
async def auth(request: Request):
    token = await oauth.google.authorize_access_token(request) #type: ignore
    userinfo = await oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token = token)#type: ignore
    user = userinfo.json()
    request.session["token"] = token
    request.session["user"] = user
    response = RedirectResponse(url = "/")
    return response

# Google Drive
@app.get("/drive")
async def drive(request: Request):
    token = await get_token(request)
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
    npt = data.get("nextPageToken")
    return templates.TemplateResponse("drive.html", {"request": request, "files": files, "nextPageToken": npt})

@app.get("/contact")
async def contacts(request: Request):
    token = await get_token(request)
    if not token:
        return RedirectResponse(url = "/login")
    contact = await oauth.google.get( #type: ignore
        "https://people.googleapis.com/v1/people/me/connections",
        params = {"personFields": "names,emailAddresses,phoneNumbers",
                  "pageSize": 15,
                  "pageToken": request.query_params.get("pageToken")
                  },
        token = token
    )
    data = contact.json()
    contact_list = data.get("connections", [])
    npt = data.get("nextPageToken")

    return templates.TemplateResponse("contact.html", {"request": request, "connections": contact_list, "nextPageToken": npt})