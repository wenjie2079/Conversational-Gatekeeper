import os
import uuid
from typing import List
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Setup OpenAI client
OpenAI.api_key = os.getenv("OPENAI_API_KEY")
OpenAI.api_base = os.getenv("OPENAI_BASE_URL")
client = OpenAI(api_key=OpenAI.api_key, base_url=OpenAI.api_base)

# User secrets database
USER_SECRET_DATABASE = {
    "alice": {
        "pet_name": "Tommy",
        "favorite_food": "Sushi",
        "shared_joke": "Knock knock banana joke"
    },
    "bob": {
        "pet_name": "Spike",
        "favorite_food": "Pizza",
        "shared_joke": "Remember that trip to Hawaii"
    }
}

# Session store
SESSIONS = {}

# FastAPI initialization
app = FastAPI()

# CORS middleware to allow frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for security in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and template setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    verdict: str = ""  # "PASS" or "FAIL"


@app.post("/start-session")
def start_session(username: str):
    username = username.lower()

    if username not in USER_SECRET_DATABASE:
        return {"error": "User not found"}

    session_id = str(uuid.uuid4())

    # Create session with secret user data
    SESSIONS[session_id] = {
        "username": username,
        "conversation_history": [
            {
                "role": "system",
                "content": f"""
You are an AI Gatekeeper tasked with verifying whether the user is truly the owner of the account named "{username}".

You have the following "secret references" that only the real {username} would know (do NOT directly reveal them to the user):
{USER_SECRET_DATABASE[username]}

Your goal:
1. Engage the user in a natural, friendly conversation to figure out whether they actually know these secrets (e.g., a specific joke, memory, or personal reference).
2. Never directly disclose the secrets. Let the user bring them up or demonstrate knowledge.
3. Maintain a casual, conversational tone while referencing these inside jokes or details.
4. If the user clearly demonstrates knowledge, conclude with [VERDICT]: PASS.
5. If they fail, conclude with [VERDICT]: FAIL.
6. Only produce a final [VERDICT] when you are certain. Do not reveal or confirm the correct info if they guess incorrectly.
7. Output the [VERDICT] only once you’ve made a final determination.
"""
            }
        ]
    }

    return {"session_id": session_id}


@app.post("/authenticate")
def authenticate(req: ChatRequest):
    session_id = req.session_id
    user_message = req.message

    if session_id not in SESSIONS:
        return {"error": "Invalid session"}

    session = SESSIONS[session_id]
    session["conversation_history"].append({"role": "user", "content": user_message})

    # Call OpenAI ChatCompletion
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session["conversation_history"]
        )
    except Exception as e:
        return {"reply": f"Error calling OpenAI API: {str(e)}", "verdict": "FAIL"}

    assistant_reply = response.choices[0].message.content
    session["conversation_history"].append({"role": "assistant", "content": assistant_reply})

    # Check for a verdict
    verdict = ""
    if "[VERDICT]:" in assistant_reply:
        if "PASS" in assistant_reply:
            verdict = "PASS"
        elif "FAIL" in assistant_reply:
            verdict = "FAIL"

    return ChatResponse(reply=assistant_reply, verdict=verdict)


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
