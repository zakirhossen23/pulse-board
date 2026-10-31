"""Boards and cards stored in DataK3 tables (schema.sql). Writes are keyed upserts, so a retry is
safe: INSERT ... ON CONFLICT (id) DO UPDATE SET col = EXCLUDED.col."""
import json
import uuid
from typing import List, Optional

from boards.domain.model import Board, Card, Role
from boards.infrastructure.dodil import connect


def _row_to_card(r) -> Card:
    # row: (id, board_id, list_name, title, description, assignee, due_date, labels, blocked_by)
    card_id, board_id, list_name, title, desc, assignee, due_date, labels_raw, blocked_raw = r
    try:
        labels = json.loads(labels_raw) if labels_raw else []
        if not isinstance(labels, list):
            labels = []
    except (ValueError, TypeError):
        labels = []

    try:
        blocked_by = json.loads(blocked_raw) if blocked_raw else []
        if not isinstance(blocked_by, list):
            blocked_by = []
    except (ValueError, TypeError):
        blocked_by = []

    return Card(
        id=card_id,
        board_id=board_id,
        list_name=list_name,
        title=title,
        description=desc or "",
        assignee=assignee,
        due_date=due_date,
        labels=labels,
        blocked_by=blocked_by
    )


class SqlBoards:
    def get(self, board_id: str) -> Optional[Board]:
        with connect() as c:
            row = c.execute("SELECT id, title, owner_email FROM boards WHERE id = %s",
                            (board_id,)).fetchone()
            if not row:
                return None
            members = c.execute("SELECT email, role FROM memberships WHERE board_id = %s",
                                (board_id,)).fetchall()
        return Board(id=row[0], title=row[1], owner_email=row[2],
                     members={e: Role(r) for e, r in members})

    def boards_for(self, email: str) -> List[Board]:
        clean_email = email.strip().lower()
        with connect() as c:
            ids = [r[0] for r in c.execute(
                "SELECT id FROM boards WHERE LOWER(owner_email) = %s "
                "UNION SELECT board_id FROM memberships WHERE LOWER(email) = %s",
                (clean_email, clean_email))]
        return [b for b in (self.get(i) for i in ids) if b]

    def save_board(self, board: Board) -> None:
        with connect() as c:
            c.execute("INSERT INTO boards (id, title, owner_email, created_at) "
                      "VALUES (%s, %s, %s, now()) ON CONFLICT (id) DO UPDATE SET "
                      "title = EXCLUDED.title, owner_email = EXCLUDED.owner_email",
                      (board.id, board.title, board.owner_email))

            # Upsert current members
            for email, role in board.members.items():
                c.execute("INSERT INTO memberships (id, board_id, email, role) "
                          "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                          "role = EXCLUDED.role",
                          (f"{board.id}:{email.lower()}", board.id, email.lower(), role.value))

            # Remove members that were removed from domain
            active_emails = [e.lower() for e in board.members.keys()]
            if active_emails:
                placeholders = ",".join(["%s"] * len(active_emails))
                c.execute(f"DELETE FROM memberships WHERE board_id = %s AND LOWER(email) NOT IN ({placeholders})",
                          [board.id] + active_emails)
            else:
                c.execute("DELETE FROM memberships WHERE board_id = %s", (board.id,))

    def delete_board(self, board_id: str) -> None:
        with connect() as c:
            c.execute("DELETE FROM activity WHERE board_id = %s", (board_id,))
            c.execute("DELETE FROM cards WHERE board_id = %s", (board_id,))
            c.execute("DELETE FROM memberships WHERE board_id = %s", (board_id,))
            c.execute("DELETE FROM boards WHERE id = %s", (board_id,))

    def get_card(self, card_id: str) -> Optional[Card]:
        with connect() as c:
            r = c.execute(
                "SELECT id, board_id, list_name, title, description, assignee, due_date, labels, blocked_by "
                "FROM cards WHERE id = %s", (card_id,)).fetchone()
        return _row_to_card(r) if r else None

    def cards_on(self, board_id: str) -> List[Card]:
        with connect() as c:
            rows = c.execute(
                "SELECT id, board_id, list_name, title, description, assignee, due_date, labels, blocked_by "
                "FROM cards WHERE board_id = %s ORDER BY updated_at ASC",
                (board_id,)).fetchall()
        return [_row_to_card(r) for r in rows]

    def save_card(self, card: Card) -> None:
        with connect() as c:
            c.execute(
                "INSERT INTO cards (id, board_id, list_name, title, description, assignee, due_date, "
                "labels, blocked_by, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET "
                "list_name = EXCLUDED.list_name, "
                "title = EXCLUDED.title, "
                "description = EXCLUDED.description, "
                "assignee = EXCLUDED.assignee, "
                "due_date = EXCLUDED.due_date, "
                "labels = EXCLUDED.labels, "
                "blocked_by = EXCLUDED.blocked_by, "
                "updated_at = EXCLUDED.updated_at",
                (card.id, card.board_id, card.list_name, card.title, card.description, card.assignee,
                 card.due_date, json.dumps(card.labels), json.dumps(card.blocked_by))
            )

    def delete_card(self, card_id: str) -> None:
        with connect() as c:
            c.execute("DELETE FROM cards WHERE id = %s", (card_id,))

    def log(self, board_id: str, card_id: Optional[str], actor: str, action: str) -> None:
        with connect() as c:
            c.execute("INSERT INTO activity (id, board_id, card_id, actor, action, event_at) "
                      "VALUES (%s, %s, %s, %s, %s, now())",
                      (uuid.uuid4().hex, board_id, card_id, actor, action))

    def activity_for_card(self, card_id: str) -> List[dict]:
        with connect() as c:
            rows = c.execute(
                "SELECT id, board_id, card_id, actor, action, to_char(event_at, 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                "FROM activity WHERE card_id = %s ORDER BY event_at DESC LIMIT 50",
                (card_id,)).fetchall()
        return [{"id": r[0], "board_id": r[1], "card_id": r[2], "actor": r[3], "action": r[4], "event_at": r[5]}
                for r in rows]

    def activity_for_board(self, board_id: str, limit: int = 50) -> List[dict]:
        with connect() as c:
            rows = c.execute(
                "SELECT id, board_id, card_id, actor, action, to_char(event_at, 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                "FROM activity WHERE board_id = %s ORDER BY event_at DESC LIMIT %s",
                (board_id, limit)).fetchall()
        return [{"id": r[0], "board_id": r[1], "card_id": r[2], "actor": r[3], "action": r[4], "event_at": r[5]}
                for r in rows]
