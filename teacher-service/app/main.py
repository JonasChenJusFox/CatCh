"""Teacher Service for CatCh cats.

Cats create fish ponds, manage problems, and invite kittens. They never join
the Cat Can Token economy, marketplace, fishing chance loop, or leaderboards.
"""

import os
import secrets
import string
from typing import Literal, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://localhost:8000")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8002")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:3000",
)
MAX_PROBLEMS_PER_POND = 100

PondVisibility = Literal["public", "private"]


class CreatePondRequest(BaseModel):
    """Request body for a cat creating a fish pond."""

    cat_id: str = Field(..., description="Teacher user id")
    name: str
    description: Optional[str] = None
    visibility: PondVisibility = "public"


class CreatePondResponse(BaseModel):
    """Response body returned after creating a fish pond."""

    pond_id: str
    name: str
    visibility: PondVisibility
    room_code: Optional[str] = None
    max_problems: int = MAX_PROBLEMS_PER_POND
    token_cost: int = 0
    cat_token_participant: bool = False


class AddProblemRequest(BaseModel):
    """Request body for adding a coding problem to a fish pond."""

    cat_id: str
    pond_id: str
    title: str
    prompt: str
    starter_code: str = ""
    reference_solution: str
    test_code: str
    topic: Optional[str] = None


class UpdateProblemRequest(BaseModel):
    """Request body for editing a coding problem in a fish pond."""

    cat_id: str
    title: str
    prompt: str
    starter_code: str = ""
    reference_solution: str
    test_code: str
    topic: Optional[str] = None


class InviteKittensRequest(BaseModel):
    """Request body for sending private pond invitations to kittens."""

    cat_id: str
    pond_id: str
    student_emails: list[str] = Field(default_factory=list)
    room_code: str


class AssignmentRequest(BaseModel):
    """Request body for creating a fish pond assignment."""

    cat_id: str
    pond_id: str
    title: str
    problem_ids: list[str]
    due_at: Optional[str] = None


class ServiceRuleResponse(BaseModel):
    """Response body describing cat role constraints."""

    role: str
    token_system_enabled: bool
    rules: list[str]


app = FastAPI(
    title="Teacher Service",
    description="CatCh cat-facing classroom and fish pond management templates",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def generate_room_code(length: int = 6) -> str:
    """Generate an uppercase private fish pond room code."""

    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def forward_to_game_service(
    method: str, path: str, payload: Optional[dict] = None
):
    """Forward a teacher action to game-service and return the JSON response."""

    async with httpx.AsyncClient() as client:
        try:
            request_kwargs = {"timeout": 10.0}
            if payload is not None:
                request_kwargs["json"] = payload
            response = await client.request(
                method, f"{GAME_SERVICE_URL}{path}", **request_kwargs
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach game-service: {exc}",
            ) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/health", tags=["health"])
async def health():
    """Return service health information."""

    return {"status": "ok", "service": "teacher-service"}


@app.get("/teacher/rules", response_model=ServiceRuleResponse, tags=["teacher"])
async def teacher_rules():
    """Return the CatCh gameplay rules for teacher users."""

    return ServiceRuleResponse(
        role="cat",
        token_system_enabled=False,
        rules=[
            "Cats create public and private fish ponds.",
            "Cats can add, edit, and delete coding problems.",
            "Cats can send private pond room codes to kittens.",
            "Cats do not earn, spend, lose, buy, or sell Cat Can Tokens.",
            "Cats are excluded from token and aquarium collection leaderboards.",
        ],
    )


@app.post("/teacher/ponds", response_model=CreatePondResponse, tags=["teacher"])
async def create_pond(payload: CreatePondRequest):
    """Create a public or private fish pond for a cat user."""

    room_code = generate_room_code() if payload.visibility == "private" else None
    forward_payload = payload.model_dump()
    forward_payload["room_code"] = room_code
    forward_payload["created_by_role"] = "cat"
    forward_payload["token_cost"] = 0

    # Template behavior: forward when game-service supports ponds, otherwise
    # return the contract shape so frontend work can proceed.
    try:
        created = await forward_to_game_service("POST", "/ponds", forward_payload)
        pond_id = (
            created.get("pond_id")
            or created.get("id")
            or f"pond_{payload.name.lower().replace(' ', '_')}"
        )
    except HTTPException as exc:
        if exc.status_code not in {404, 502}:
            raise
        pond_id = f"pond_{payload.name.lower().replace(' ', '_')}"

    return CreatePondResponse(
        pond_id=pond_id,
        name=payload.name,
        visibility=payload.visibility,
        room_code=room_code,
    )


@app.get("/teacher/{cat_id}/ponds", tags=["teacher"])
async def list_teacher_ponds(cat_id: str):
    """Return classrooms created by one cat user."""

    try:
        return await forward_to_game_service("GET", f"/ponds/teacher/{cat_id}")
    except HTTPException as exc:
        if exc.status_code not in {404, 502}:
            raise
        return []


@app.get("/teacher/ponds/{pond_id}/problems", tags=["teacher"])
async def list_pond_problems(pond_id: str):
    """Return problems created inside one teacher fish pond."""

    try:
        return await forward_to_game_service("GET", f"/ponds/{pond_id}/problems")
    except HTTPException as exc:
        if exc.status_code not in {404, 502}:
            raise
        return []


@app.post("/teacher/ponds/{pond_id}/problems", tags=["teacher"])
async def add_problem(pond_id: str, payload: AddProblemRequest):
    """Add a teacher-authored coding problem to a fish pond."""

    if payload.pond_id != pond_id:
        raise HTTPException(status_code=400, detail="pond_id path/body mismatch")

    forward_payload = payload.model_dump()
    forward_payload["created_by_role"] = "cat"
    forward_payload["fishing_reward"] = 1
    forward_payload["cat_token_reward"] = 0

    try:
        return await forward_to_game_service(
            "POST", f"/ponds/{pond_id}/problems", forward_payload
        )
    except HTTPException as exc:
        if exc.status_code not in {404, 502}:
            raise
        return {
            "status": "queued_template",
            "pond_id": pond_id,
            "problem": forward_payload,
            "max_problems_per_pond": MAX_PROBLEMS_PER_POND,
        }


@app.put("/teacher/ponds/{pond_id}/problems/{problem_id}", tags=["teacher"])
async def update_problem(pond_id: str, problem_id: str, payload: UpdateProblemRequest):
    """Edit a teacher-authored coding problem in a fish pond."""

    forward_payload = payload.model_dump()
    forward_payload["created_by_role"] = "cat"
    forward_payload["fishing_reward"] = 1
    forward_payload["cat_token_reward"] = 0

    return await forward_to_game_service(
        "PUT", f"/ponds/{pond_id}/problems/{problem_id}", forward_payload
    )


@app.delete("/teacher/ponds/{pond_id}/problems/{problem_id}", tags=["teacher"])
async def delete_problem(pond_id: str, problem_id: str, cat_id: str):
    """Delete a teacher-authored coding problem from a fish pond."""

    escaped_cat_id = quote(cat_id, safe="")
    return await forward_to_game_service(
        "DELETE", f"/ponds/{pond_id}/problems/{problem_id}?cat_id={escaped_cat_id}"
    )


@app.post("/teacher/ponds/{pond_id}/assignments", tags=["teacher"])
async def create_assignment(pond_id: str, payload: AssignmentRequest):
    """Create an assignment from problems already in a fish pond."""

    if payload.pond_id != pond_id:
        raise HTTPException(status_code=400, detail="pond_id path/body mismatch")
    if len(payload.problem_ids) > MAX_PROBLEMS_PER_POND:
        raise HTTPException(
            status_code=400, detail="A fish pond can contain at most 100 problems"
        )

    try:
        return await forward_to_game_service(
            "POST", f"/ponds/{pond_id}/assignments", payload.model_dump()
        )
    except HTTPException as exc:
        if exc.status_code not in {404, 502}:
            raise
        return {"status": "queued_template", "assignment": payload.model_dump()}


@app.post("/teacher/ponds/{pond_id}/invites", tags=["teacher"])
async def invite_kittens(pond_id: str, payload: InviteKittensRequest):
    """Prepare a private fish pond room code invitation for kittens."""

    if payload.pond_id != pond_id:
        raise HTTPException(status_code=400, detail="pond_id path/body mismatch")
    return {
        "status": "template_ready",
        "pond_id": pond_id,
        "room_code": payload.room_code,
        "student_emails": payload.student_emails,
        "email_service": AUTH_SERVICE_URL,
        "message": "Send this room code to kittens through the invitation flow.",
    }
