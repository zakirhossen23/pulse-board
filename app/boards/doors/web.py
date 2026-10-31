"""The web door: JSON routes plus a responsive, feature-rich Kanban web UI.
Every route calls a use case and nothing else.
"""
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from boards.application.use_cases import Boards, NotFound
from boards.doors.identity import person_from
from boards.domain.model import Forbidden, Invalid, Person

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def load_static(filename: str) -> str:
    path = STATIC_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def build_router(boards: Boards) -> APIRouter:
    r = APIRouter()

    def me(request: Request) -> Person:
        p = person_from(request.headers)
        if p is None:
            raise HTTPException(401, "sign in first: /.dodil/auth/login")
        return p

    def run(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFound as e:
            raise HTTPException(404, str(e))
        except Forbidden as e:
            raise HTTPException(403, str(e))
        except Invalid as e:
            raise HTTPException(422, str(e))

    class Title(BaseModel):
        title: str

    class CardIn(BaseModel):
        title: str
        list_name: str = "To do"
        description: str = ""
        assignee: Optional[str] = None
        due_date: Optional[str] = None
        labels: Optional[List[str]] = None
        blocked_by: Optional[List[str]] = None

    class CardUpdate(BaseModel):
        title: Optional[str] = None
        description: Optional[str] = None
        assignee: Optional[str] = None
        due_date: Optional[str] = None
        labels: Optional[List[str]] = None
        blocked_by: Optional[List[str]] = None

    class Move(BaseModel):
        list_name: str

    class Member(BaseModel):
        email: str
        role: str = "member"

    @r.get("/api/me")
    def current_user(request: Request):
        p = person_from(request.headers)
        if p is None:
            return {"signed_in": False, "email": None}
        return {"signed_in": True, "email": p.email}

    @r.get("/api/boards")
    def my_boards(request: Request):
        return run(boards.my_boards, me(request))

    @r.post("/api/boards", status_code=201)
    def create_board(body: Title, request: Request):
        return run(boards.create_board, me(request), body.title)

    @r.get("/api/boards/{board_id}")
    def show_board(board_id: str, request: Request):
        return run(boards.show_board, me(request), board_id)

    @r.post("/api/boards/{board_id}/members", status_code=201)
    def add_member(board_id: str, body: Member, request: Request):
        return run(boards.add_member, me(request), board_id, body.email, body.role)

    @r.delete("/api/boards/{board_id}/members/{email}")
    def remove_member(board_id: str, email: str, request: Request):
        return run(boards.remove_member, me(request), board_id, email)

    @r.get("/api/boards/{board_id}/activity")
    def board_activity(board_id: str, request: Request):
        return run(boards.board_history, me(request), board_id)

    @r.get("/api/boards/{board_id}/summary")
    def board_summary(board_id: str, request: Request):
        return run(boards.board_summary, me(request), board_id)

    @r.get("/api/boards/{board_id}/blocking")
    def board_blocking(board_id: str, request: Request):
        return run(boards.what_is_blocking, me(request), board_id=board_id)

    @r.post("/api/boards/{board_id}/cards", status_code=201)
    def add_card(board_id: str, body: CardIn, request: Request):
        return run(boards.add_card, me(request), board_id, body.title,
                   list_name=body.list_name, description=body.description,
                   assignee=body.assignee, due_date=body.due_date,
                   labels=body.labels, blocked_by=body.blocked_by)

    @r.get("/api/cards/my")
    def my_cards(request: Request, this_week: bool = Query(False)):
        return run(boards.list_my_cards, me(request), only_due_this_week=this_week)

    @r.get("/api/cards/overdue")
    def overdue_cards(request: Request, board_id: Optional[str] = Query(None)):
        return run(boards.list_overdue, me(request), board_id=board_id)

    @r.post("/api/cards/{card_id}/move")
    def move_card(card_id: str, body: Move, request: Request):
        return run(boards.move_card, me(request), card_id, body.list_name)

    @r.patch("/api/cards/{card_id}")
    def update_card(card_id: str, body: CardUpdate, request: Request):
        return run(boards.update_card, me(request), card_id,
                   title=body.title, description=body.description,
                   assignee=body.assignee, due_date=body.due_date,
                   labels=body.labels, blocked_by=body.blocked_by)

    @r.delete("/api/cards/{card_id}")
    def delete_card(card_id: str, request: Request):
        return run(boards.delete_card, me(request), card_id)

    @r.get("/api/cards/{card_id}/history")
    def card_history(card_id: str, request: Request):
        return run(boards.card_history, me(request), card_id)

    @r.get("/api/cards/{card_id}/blocking")
    def card_blocking(card_id: str, request: Request):
        return run(boards.what_is_blocking, me(request), card_id=card_id)

    @r.post("/api/cards/{card_id}/checklist")
    def suggest_checklist(card_id: str, request: Request):
        return run(boards.suggest_checklist, me(request), card_id)

    @r.get("/api/cards/{card_id}/similar")
    def find_similar(card_id: str, request: Request):
        return run(boards.find_similar_cards, me(request), card_id)

    @r.get("/favicon.ico", include_in_schema=False)
    def favicon():
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">⚡</text></svg>'
        return Response(content=svg, media_type="image/svg+xml")

    @r.get("/static/app.js")
    def serve_app_js():
        return Response(content=load_static("app.js"), media_type="application/javascript")

    @r.get("/", response_class=HTMLResponse)
    def page(request: Request):
        if person_from(request.headers) is None:
            return RedirectResponse("/.dodil/auth/login?return_to=/", status_code=303)
        return HTMLResponse(content=load_static("index.html"))

    return r
