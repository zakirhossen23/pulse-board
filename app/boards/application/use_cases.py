"""Every action a person can take. The web routes and the MCP tools both call these and nothing
else, so a rule cannot be skipped by using the other door.

Add a use case here, then expose it in doors/web.py and doors/mcp.py (one line each).
"""
import uuid
from dataclasses import asdict
from datetime import date, timedelta
from typing import List, Optional

from boards.application.ports import Assistant, BoardRepository
from boards.domain.model import Board, Card, Forbidden, Invalid, Person, Role


class NotFound(Exception):
    pass


def _card(c: Card) -> dict:
    d = asdict(c)
    d["due_date"] = c.due_date.isoformat() if c.due_date else None
    d["is_overdue"] = c.is_overdue()
    return d


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip())
    except (ValueError, TypeError):
        raise Invalid(f"invalid date format {val!r}, expected YYYY-MM-DD")


class Boards:
    def __init__(self, repo: BoardRepository, assistant: Optional[Assistant] = None):
        self.repo, self.assistant = repo, assistant

    def _board(self, board_id: str, person: Person) -> Board:
        board = self.repo.get(board_id)
        if board is None:
            raise NotFound("no such board")
        try:
            board.require_view(person)
        except Forbidden:
            raise NotFound("no such board")  # a board you can't see doesn't exist for you
        return board

    def _find_card(self, card_id: str, person: Person) -> tuple[Board, Card]:
        card = self.repo.get_card(card_id)
        if card is None:
            raise NotFound("no such card")
        return self._board(card.board_id, person), card

    def create_board(self, person: Person, title: str) -> dict:
        clean_title = title.strip()
        if not clean_title:
            raise Invalid("a board needs a title")
        board = Board(id=uuid.uuid4().hex[:12], title=clean_title, owner_email=person.email.lower())
        self.repo.save_board(board)
        self.repo.log(board.id, None, person.email, f"created board {board.title!r}")
        return {"id": board.id, "title": board.title, "owner_email": board.owner_email, "role": "owner"}

    def my_boards(self, person: Person) -> List[dict]:
        boards = self.repo.boards_for(person.email)
        return [{"id": b.id, "title": b.title, "owner_email": b.owner_email, "role": b.role_of(person).value}
                for b in boards]

    def show_board(self, person: Person, board_id: str) -> dict:
        board = self._board(board_id, person)
        cards = [_card(c) for c in self.repo.cards_on(board.id)]
        members = [{"email": board.owner_email, "role": "owner"}] + [
            {"email": e, "role": r.value} for e, r in sorted(board.members.items())
        ]
        return {
            "id": board.id,
            "title": board.title,
            "owner_email": board.owner_email,
            "role": board.role_of(person).value,
            "members": members,
            "cards": cards
        }

    def add_member(self, person: Person, board_id: str, email: str, role: str = "member") -> dict:
        board = self._board(board_id, person)
        clean_email = email.strip().lower()
        try:
            role_enum = Role(role.strip().lower())
        except ValueError:
            raise Invalid(f"unknown role {role!r}; roles are member or viewer")
        board.add_member(person, clean_email, role_enum)
        self.repo.save_board(board)
        self.repo.log(board.id, None, person.email, f"added {clean_email} as {role_enum.value}")
        return {"board_id": board.id, "email": clean_email, "role": role_enum.value}

    def remove_member(self, person: Person, board_id: str, email: str) -> dict:
        board = self._board(board_id, person)
        clean_email = email.strip().lower()
        board.remove_member(person, clean_email)
        self.repo.save_board(board)
        self.repo.log(board.id, None, person.email, f"removed member {clean_email}")
        return {"board_id": board.id, "email": clean_email, "removed": True}

    def add_card(self, person: Person, board_id: str, title: str,
                 list_name: str = "To do", description: str = "",
                 assignee: Optional[str] = None, due_date: Optional[str] = None,
                 labels: Optional[List[str]] = None,
                 blocked_by: Optional[List[str]] = None) -> dict:
        board = self._board(board_id, person)
        board.require_edit(person)
        clean_title = title.strip()
        if not clean_title:
            raise Invalid("card title is required")

        parsed_date = _parse_date(due_date) if due_date else None
        clean_assignee = assignee.strip().lower() if assignee and assignee.strip() else None

        card = Card(
            id=uuid.uuid4().hex[:12],
            board_id=board.id,
            title=clean_title,
            description=description.strip() if description else "",
            assignee=clean_assignee,
            due_date=parsed_date,
            labels=[lbl.strip() for lbl in (labels or []) if lbl and lbl.strip()],
            blocked_by=[b.strip() for b in (blocked_by or []) if b and b.strip()]
        )
        card.move_to(list_name)
        self.repo.save_card(card)
        self.repo.log(board.id, card.id, person.email, f"added card {card.title!r} to {list_name}")
        return _card(card)

    def move_card(self, person: Person, card_id: str, list_name: str) -> dict:
        board, card = self._find_card(card_id, person)
        board.require_edit(person)
        before = card.list_name
        card.move_to(list_name)
        self.repo.save_card(card)
        self.repo.log(board.id, card.id, person.email, f"moved card from {before} to {list_name}")
        return _card(card)

    def update_card(self, person: Person, card_id: str,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    assignee: Optional[str] = None,
                    due_date: Optional[str] = None,
                    labels: Optional[List[str]] = None,
                    blocked_by: Optional[List[str]] = None) -> dict:
        board, card = self._find_card(card_id, person)
        board.require_edit(person)

        changes = []
        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise Invalid("card title cannot be empty")
            if clean_title != card.title:
                changes.append(f"renamed title to {clean_title!r}")
                card.title = clean_title

        if description is not None and description != card.description:
            changes.append("updated description")
            card.description = description

        if assignee is not None:
            clean_assignee = assignee.strip().lower() if assignee.strip() else None
            if clean_assignee != card.assignee:
                changes.append(f"assigned to {clean_assignee or 'nobody'}")
                card.assignee = clean_assignee

        if due_date is not None:
            parsed_date = _parse_date(due_date) if str(due_date).strip() else None
            if parsed_date != card.due_date:
                changes.append(f"due date set to {parsed_date.isoformat() if parsed_date else 'none'}")
                card.due_date = parsed_date

        if labels is not None:
            clean_labels = [l.strip() for l in labels if l and l.strip()]
            if clean_labels != card.labels:
                changes.append(f"labels set to {clean_labels}")
                card.labels = clean_labels

        if blocked_by is not None:
            clean_blockers = [b.strip() for b in blocked_by if b and b.strip() and b.strip() != card.id]
            if clean_blockers != card.blocked_by:
                changes.append(f"dependencies updated to {clean_blockers}")
                card.blocked_by = clean_blockers

        self.repo.save_card(card)
        if changes:
            self.repo.log(board.id, card.id, person.email, "; ".join(changes))
        return _card(card)

    def assign_card(self, person: Person, card_id: str, assignee: Optional[str]) -> dict:
        return self.update_card(person, card_id, assignee=assignee or "")

    def delete_card(self, person: Person, card_id: str) -> dict:
        board, card = self._find_card(card_id, person)
        board.require_edit(person)
        self.repo.delete_card(card.id)
        self.repo.log(board.id, card.id, person.email, f"deleted card {card.title!r}")
        return {"id": card.id, "deleted": True}

    def card_history(self, person: Person, card_id: str) -> List[dict]:
        self._find_card(card_id, person)
        return self.repo.activity_for_card(card_id)

    def board_history(self, person: Person, board_id: str) -> List[dict]:
        board = self._board(board_id, person)
        return self.repo.activity_for_board(board.id)

    def list_my_cards(self, person: Person, only_due_this_week: bool = False) -> List[dict]:
        """Cards assigned to the person across all boards they have access to."""
        my_boards = self.repo.boards_for(person.email)
        results = []
        today = date.today()
        week_end = today + timedelta(days=7)

        for b in my_boards:
            for card in self.repo.cards_on(b.id):
                if card.assignee and card.assignee.lower() == person.email.lower():
                    if only_due_this_week:
                        if not card.due_date or not (today <= card.due_date <= week_end):
                            continue
                    c_dict = _card(card)
                    c_dict["board_title"] = b.title
                    results.append(c_dict)
        return results

    def list_overdue(self, person: Person, board_id: Optional[str] = None) -> List[dict]:
        """Overdue cards (past due_date and not in 'Done') across visible boards."""
        if board_id:
            boards = [self._board(board_id, person)]
        else:
            boards = self.repo.boards_for(person.email)

        overdue_cards = []
        for b in boards:
            for card in self.repo.cards_on(b.id):
                if card.is_overdue():
                    c_dict = _card(card)
                    c_dict["board_title"] = b.title
                    overdue_cards.append(c_dict)
        return overdue_cards

    def what_is_blocking(self, person: Person, card_id: Optional[str] = None,
                         board_id: Optional[str] = None) -> dict:
        """Card dependencies check: find blockers for a specific card or across a board."""
        if card_id:
            board, card = self._find_card(card_id, person)
            blockers = []
            for b_id in card.blocked_by:
                b_card = self.repo.get_card(b_id)
                if b_card:
                    blockers.append({
                        "id": b_card.id,
                        "title": b_card.title,
                        "list_name": b_card.list_name,
                        "is_done": b_card.list_name == "Done",
                        "assignee": b_card.assignee
                    })
            return {
                "card_id": card.id,
                "card_title": card.title,
                "list_name": card.list_name,
                "is_blocked": any(not b["is_done"] for b in blockers),
                "blockers": blockers
            }

        if board_id:
            board = self._board(board_id, person)
            cards = self.repo.cards_on(board.id)
            cards_by_id = {c.id: c for c in cards}
            blocked_cards = []

            for c in cards:
                if c.blocked_by:
                    unresolved = []
                    for b_id in c.blocked_by:
                        b_card = cards_by_id.get(b_id) or self.repo.get_card(b_id)
                        if b_card and b_card.list_name != "Done":
                            unresolved.append({"id": b_card.id, "title": b_card.title, "list_name": b_card.list_name})
                    if unresolved:
                        blocked_cards.append({
                            "card_id": c.id,
                            "title": c.title,
                            "list_name": c.list_name,
                            "blocked_by": unresolved
                        })

            return {"board_id": board.id, "board_title": board.title, "blocked_cards": blocked_cards}

        raise Invalid("must specify card_id or board_id")

    def suggest_checklist(self, person: Person, card_id: str) -> dict:
        """An AI suggestion: generates 3-6 actionable sub-tasks for a card."""
        _, card = self._find_card(card_id, person)
        if self.assistant is None:
            raise Invalid("no AI assistant configured")
        items = self.assistant.checklist(card.title)
        return {"card_id": card.id, "title": card.title, "suggested_checklist": items}

    def board_summary(self, person: Person, board_id: str) -> dict:
        """AI-generated concise daily summary of board status, workload, and overdue items."""
        board = self._board(board_id, person)
        if self.assistant is None:
            raise Invalid("no AI assistant configured")
        cards = self.repo.cards_on(board.id)
        cards_summary = "\n".join([
            f"- [{c.list_name}] {c.title} (Assignee: {c.assignee or 'unassigned'}, Due: {c.due_date or 'none'}, Overdue: {c.is_overdue()})"
            for c in cards
        ])
        summary_text = self.assistant.summary(board.title, cards_summary)
        return {"board_id": board.id, "board_title": board.title, "summary": summary_text}

    def find_similar_cards(self, person: Person, card_id: str) -> dict:
        """Finds cards on the same board with related or overlapping topics using AI."""
        board, card = self._find_card(card_id, person)
        if self.assistant is None:
            raise Invalid("no AI assistant configured")
        other_cards = [{"id": c.id, "title": c.title, "list_name": c.list_name}
                       for c in self.repo.cards_on(board.id) if c.id != card.id]
        if not other_cards:
            return {"card_id": card.id, "similar_cards": []}
        matches = self.assistant.find_similar(card.title, other_cards)
        return {"card_id": card.id, "card_title": card.title, "similar_cards": matches}
