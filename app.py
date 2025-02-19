import os
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from openai import OpenAI

# Load environment variables
load_dotenv()

# Setup OpenAI client
OpenAI.api_key = os.getenv("OPENAI_API_KEY")
OpenAI.api_base = os.getenv("OPENAI_BASE_URL")
client = OpenAI(api_key=OpenAI.api_key, base_url=OpenAI.api_base)

# Your user secrets database
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

# FastAPI initialization
app = FastAPI()

# Add these lines after app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Define schemas for requests and responses
class Message(BaseModel):
    role: str  # "user", "assistant", or "system"
    content: str

class ChatRequest(BaseModel):
    username: str
    messages: List[Message]

class ChatResponse(BaseModel):
    reply: str
    verdict: str = ""  # optional, can be "PASS", "FAIL", or empty if no verdict yet


@app.post("/authenticate", response_model=ChatResponse)
def authenticate(req: ChatRequest):
    """
    This endpoint receives the conversation history (including the latest user message),
    then calls the OpenAI API with our "AI Gatekeeper" logic. 
    We inject a special system prompt based on the user's secret info.
    """

    username = req.username.lower()
    user_secrets = USER_SECRET_DATABASE.get(username)

    # If no secret info for the given user, return an immediate fail
    if not user_secrets:
        return ChatResponse(
            reply="I'm sorry, I can't find any record of your account. Access denied.",
            verdict="FAIL"
        )

    # Build a "system prompt" that includes the user's secrets (without revealing them!)
    system_prompt = f"""
You are an AI Gatekeeper tasked with verifying whether the user is truly the owner of the account named "{username}."

You have the following "secret references" that only the real {username} would know (do NOT directly reveal them to the user):
{user_secrets}

Your goal:
1. **Engage** the user in a natural, friendly conversation to figure out whether they actually know these secrets (e.g., a specific joke, memory, or personal reference).
2. **Never** directly disclose the secrets. Let the user bring them up or demonstrate knowledge.
3. Maintain a casual, conversational tone while referencing these inside jokes or details.
4. If the user clearly demonstrates knowledge, conclude with `[VERDICT]: PASS`.
5. If they fail, conclude with `[VERDICT]: FAIL`.
6. Only produce a final `[VERDICT]` when you are certain. Do not reveal or confirm the correct info if they guess incorrectly.
7. Output the `[VERDICT]` only once you’ve made a final determination.
""".strip()

    # Construct the conversation for OpenAI:
    # Start with the system prompt, followed by the messages from the client
    conversation_history = [{"role": "system", "content": system_prompt}]
    for m in req.messages:
        conversation_history.append({"role": m.role, "content": m.content})

    # Call OpenAI ChatCompletion
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo", "gpt-4", etc.
            messages=conversation_history
        )
    except Exception as e:
        # If an error occurs (network, invalid API key, etc.), handle gracefully
        return ChatResponse(
            reply=f"Error calling OpenAI API: {str(e)}",
            verdict="FAIL"
        )

    # Extract the assistant's message
    assistant_reply = response.choices[0].message.content

    # Check for a verdict in the assistant's reply
    verdict = ""
    if "[VERDICT]:" in assistant_reply:
        # Example: if the AI replies: "Thanks for clarifying. [VERDICT]: PASS"
        split_text = assistant_reply.split("[VERDICT]:")
        # The part after "[VERDICT]:" might be something like " PASS"
        verdict_text = split_text[-1].strip().upper()
        if "PASS" in verdict_text:
            verdict = "PASS"
        else:
            verdict = "FAIL"

    # Return the assistant's reply and any verdict found
    return ChatResponse(reply=assistant_reply, verdict=verdict)


# Add this new route
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
