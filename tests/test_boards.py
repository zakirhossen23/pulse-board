"""The board's rules, through the use cases and both doors. No Dodil account needed:
the repository and the AI are in-memory fakes.
"""
from datetime import date, timedelta
import json
import pytest
from fastapi.testclient import TestClient

from boards.application.use_cases import Boards, NotFound
from boards.domain.model import Forbidden, Invalid, Person
from boards.main import create_app

OWNER, MEMBER, VIEWER, STRANGER = (Person(e) for e in
                                   ("ana@x.io", "bo@x.io", "cy@x.io", "dee@x.io"))


class MemoryBoards:
    def __init__(self):
        self.boards = {}
        self.cards = {}
        self.events = []

    def get(self, board_id):
        return self.boards.get(board_id)

    def boards_for(self, email):
        clean = email.lower()
        return [b for b in self.boards.values() if b.owner_email.lower() == clean or clean in b.members]

    def save_board(self, board):
        self.boards[board.id] = board

    def delete_board(self, board_id):
        self.boards.pop(board_id, None)

    def get_card(self, card_id):
        return self.cards.get(card_id)

    def cards_on(self, board_id):
        return [c for c in self.cards.values() if c.board_id == board_id]

    def save_card(self, card):
        self.cards[card.id] = card

    def delete_card(self, card_id):
        self.cards.pop(card_id, None)

    def log(self, board_id, card_id, actor, action):
        self.events.append({
            "id": f"evt-{len(self.events)}",
            "board_id": board_id,
            "card_id": card_id,
            "actor": actor,
            "action": action,
            "event_at": "2026-10-31T12:00:00Z"
        })

    def activity_for_card(self, card_id):
        return [e for e in reversed(self.events) if e["card_id"] == card_id]

    def activity_for_board(self, board_id, limit=50):
        return [e for e in reversed(self.events) if e["board_id"] == board_id][:limit]


class FakeAI:
    def checklist(self, title):
        return ["Write unit tests", "Run integration tests", "Deploy to Dodil"]

    def summary(self, board_title, cards_summary):
        return f"Daily standup summary for {board_title}: All systems go."

    def find_similar(self, target_title, candidate_titles):
        return [{"id": c["id"], "title": c["title"], "reason": "Keyword match"}
                for c in candidate_titles if "deploy" in c["title"].lower() or "test" in c["title"].lower()]


@pytest.fixture
def svc():
    s = Boards(MemoryBoards(), FakeAI())
    b = s.create_board(OWNER, "Launch")
    s.add_member(OWNER, b["id"], MEMBER.email, "member")
    s.add_member(OWNER, b["id"], VIEWER.email, "viewer")
    return s, b["id"]


def test_member_adds_and_moves_cards_and_it_is_logged(svc):
    s, bid = svc
    card = s.add_card(MEMBER, bid, "Send invoice")
    moved = s.move_card(MEMBER, card["id"], "Done")
    assert moved["list_name"] == "Done"
    assert any("moved card from To do to Done" in e["action"] for e in s.repo.events)


def test_viewer_cannot_edit(svc):
    s, bid = svc
    with pytest.raises(Forbidden):
        s.add_card(VIEWER, bid, "nope")


def test_only_owner_manages_members(svc):
    s, bid = svc
    with pytest.raises(Forbidden):
        s.add_member(MEMBER, bid, "eve@x.io", "member")


def test_owner_removes_member(svc):
    s, bid = svc
    res = s.remove_member(OWNER, bid, MEMBER.email)
    assert res["removed"] is True
    # Once removed, bo cannot even see that the board exists
    with pytest.raises(NotFound):
        s.add_card(MEMBER, bid, "now blocked")


def test_stranger_cannot_see_board(svc):
    s, bid = svc
    with pytest.raises(NotFound):
        s.show_board(STRANGER, bid)
    assert s.my_boards(STRANGER) == []


def test_unknown_list_is_refused(svc):
    s, bid = svc
    card = s.add_card(OWNER, bid, "x")
    with pytest.raises(Invalid):
        s.move_card(OWNER, card["id"], "Someday")


def test_card_details_and_updates(svc):
    s, bid = svc
    card = s.add_card(
        MEMBER, bid, "Setup DataK3",
        description="Configure postgres TLS",
        assignee=MEMBER.email,
        due_date="2026-11-10",
        labels=["database", "p0"]
    )
    assert card["description"] == "Configure postgres TLS"
    assert card["assignee"] == MEMBER.email
    assert card["due_date"] == "2026-11-10"
    assert card["labels"] == ["database", "p0"]

    # Update card
    updated = s.update_card(
        MEMBER, card["id"],
        title="Setup DataK3 & Bucket",
        due_date="2026-11-15",
        labels=["database", "completed"]
    )
    assert updated["title"] == "Setup DataK3 & Bucket"
    assert updated["due_date"] == "2026-11-15"
    assert updated["labels"] == ["database", "completed"]

    # Verify history
    history = s.card_history(MEMBER, card["id"])
    assert len(history) >= 2


def test_overdue_cards_detection(svc):
    s, bid = svc
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    c1 = s.add_card(OWNER, bid, "Late task", due_date=yesterday)
    c2 = s.add_card(OWNER, bid, "Future task", due_date=tomorrow)
    c3 = s.add_card(OWNER, bid, "Finished late task", due_date=yesterday, list_name="Done")

    overdue = s.list_overdue(OWNER, bid)
    overdue_ids = [c["id"] for c in overdue]
    assert c1["id"] in overdue_ids
    assert c2["id"] not in overdue_ids
    assert c3["id"] not in overdue_ids


def test_my_cards_filtering(svc):
    s, bid = svc
    today = date.today().isoformat()
    in_three_days = (date.today() + timedelta(days=3)).isoformat()
    in_thirty_days = (date.today() + timedelta(days=30)).isoformat()

    s.add_card(MEMBER, bid, "Task for Bo soon", assignee=MEMBER.email, due_date=in_three_days)
    s.add_card(MEMBER, bid, "Task for Bo far", assignee=MEMBER.email, due_date=in_thirty_days)
    s.add_card(MEMBER, bid, "Task for Ana", assignee=OWNER.email, due_date=today)

    bo_all = s.list_my_cards(MEMBER, only_due_this_week=False)
    assert len(bo_all) == 2

    bo_this_week = s.list_my_cards(MEMBER, only_due_this_week=True)
    assert len(bo_this_week) == 1
    assert bo_this_week[0]["title"] == "Task for Bo soon"


def test_card_dependencies_and_blockers(svc):
    s, bid = svc
    card_backend = s.add_card(MEMBER, bid, "Build API backend")
    card_frontend = s.add_card(MEMBER, bid, "Build Frontend UI", blocked_by=[card_backend["id"]])

    # Check card blocker status
    res = s.what_is_blocking(MEMBER, card_id=card_frontend["id"])
    assert res["is_blocked"] is True
    assert len(res["blockers"]) == 1
    assert res["blockers"][0]["id"] == card_backend["id"]

    # Check board level blocking
    board_res = s.what_is_blocking(MEMBER, board_id=bid)
    assert len(board_res["blocked_cards"]) == 1

    # Resolve blocker
    s.move_card(MEMBER, card_backend["id"], "Done")
    res_after = s.what_is_blocking(MEMBER, card_id=card_frontend["id"])
    assert res_after["is_blocked"] is False


def test_ai_features(svc):
    s, bid = svc
    card = s.add_card(MEMBER, bid, "Deploy project to Dodil")
    s.add_card(MEMBER, bid, "Run integration tests")

    checklist = s.suggest_checklist(MEMBER, card["id"])
    assert "Deploy to Dodil" in checklist["suggested_checklist"]

    summary = s.board_summary(MEMBER, bid)
    assert "Daily standup summary" in summary["summary"]

    similar = s.find_similar_cards(MEMBER, card["id"])
    assert len(similar["similar_cards"]) >= 1


def test_card_deletion_and_history(svc):
    s, bid = svc
    card = s.add_card(MEMBER, bid, "Temporary note")
    cid = card["id"]
    hist = s.card_history(MEMBER, cid)
    assert len(hist) >= 1
    assert any("added card" in h["action"] for h in hist)

    # Delete card
    del_res = s.delete_card(MEMBER, cid)
    assert del_res["deleted"] is True

    # Card can no longer be found
    with pytest.raises(NotFound):
        s.move_card(MEMBER, cid, "Done")


def _h(p):
    return {"X-Dodil-User": json.dumps({"sub": p.email, "email": p.email})}


def test_web_and_mcp_doors_share_the_rules(svc):
    s, bid = svc
    with TestClient(create_app(s)) as c:
        # Auth check
        assert c.get("/api/boards").status_code == 401
        assert c.get("/api/boards", headers=_h(VIEWER)).json()[0]["role"] == "viewer"
        assert c.post(f"/api/boards/{bid}/cards", json={"title": "t"},
                      headers=_h(VIEWER)).status_code == 403

        # MCP check
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401 and "resource_metadata" in r.headers["www-authenticate"]
        mcp_h = {**_h(MEMBER), "accept": "application/json, text/event-stream"}

        # Initialize MCP
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}}}
        assert c.post("/mcp", json=init, headers=mcp_h).status_code == 200

        # Call add_card via MCP
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "add_card", "arguments": {
                    "board_id": bid,
                    "title": "via mcp",
                    "description": "added from assistant",
                    "assignee": MEMBER.email
                }}}
        out = c.post("/mcp", json=call, headers=mcp_h).json()
        assert not out["result"].get("isError"), out
        assert any(c.title == "via mcp" for c in s.repo.cards.values())

        # Call my_cards via MCP
        call_my = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "my_cards", "arguments": {"only_due_this_week": False}}}
        out_my = c.post("/mcp", json=call_my, headers=mcp_h).json()
        assert not out_my["result"].get("isError"), out_my
        content = out_my["result"].get("content", [])
        assert len(content) > 0

        # Web API endpoints checks
        # My cards web API
        res_my = c.get("/api/cards/my", headers=_h(MEMBER))
        assert res_my.status_code == 200

        # Overdue web API
        res_overdue = c.get("/api/cards/overdue", headers=_h(MEMBER))
        assert res_overdue.status_code == 200

        # Board activity web API
        res_act = c.get(f"/api/boards/{bid}/activity", headers=_h(MEMBER))
        assert res_act.status_code == 200

        # Board summary web API
        res_sum = c.get(f"/api/boards/{bid}/summary", headers=_h(MEMBER))
        assert res_sum.status_code == 200
        assert "Daily standup summary" in res_sum.json()["summary"]

        # Board blocking web API
        res_blk = c.get(f"/api/boards/{bid}/blocking", headers=_h(MEMBER))
        assert res_blk.status_code == 200
