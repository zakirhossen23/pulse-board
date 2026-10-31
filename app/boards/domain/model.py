"""The board's language and rules. No database, no HTTP: plain Python you can test in a second.

Extend HERE first: a rule written in the domain holds for the web page and for Claude alike.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

LISTS = ("To do", "Doing", "Done")


class Role(str, Enum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class Forbidden(Exception):
    """The person may not do this. The doors turn it into 403 (web) or a tool error (MCP)."""


class Invalid(Exception):
    """The request breaks a rule of the board itself. 422 / tool error."""


@dataclass(frozen=True)
class Person:
    """Who is acting: taken from the gateway's sign-in, never from the request body."""
    email: str


@dataclass
class Card:
    id: str
    board_id: str
    title: str
    list_name: str = LISTS[0]
    description: str = ""
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    labels: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)

    def move_to(self, list_name: str) -> None:
        if list_name not in LISTS:
            raise Invalid(f"unknown list {list_name!r}; lists are {', '.join(LISTS)}")
        self.list_name = list_name

    def is_overdue(self, today: Optional[date] = None) -> bool:
        if not self.due_date:
            return False
        if self.list_name == "Done":
            return False
        ref = today or date.today()
        return self.due_date < ref


@dataclass
class Board:
    id: str
    title: str
    owner_email: str
    members: dict = field(default_factory=dict)  # email -> Role

    def role_of(self, person: Person) -> Optional[Role]:
        if person.email.lower() == self.owner_email.lower():
            return Role.OWNER
        return self.members.get(person.email.lower())

    def require_view(self, person: Person) -> None:
        if self.role_of(person) is None:
            raise Forbidden("you are not on this board")

    def require_edit(self, person: Person) -> None:
        role = self.role_of(person)
        if role is None:
            raise Forbidden("you are not on this board")
        if role is Role.VIEWER:
            raise Forbidden("viewers can't change the board")

    def require_owner(self, person: Person) -> None:
        if self.role_of(person) is not Role.OWNER:
            raise Forbidden("only the owner manages members")

    def add_member(self, by: Person, email: str, role: Role) -> None:
        self.require_owner(by)
        email_clean = email.strip().lower()
        if not email_clean:
            raise Invalid("member email is required")
        if email_clean == self.owner_email.lower():
            raise Invalid("owner is already on the board")
        if role is Role.OWNER:
            raise Invalid("a board has one owner")
        self.members[email_clean] = role

    def remove_member(self, by: Person, email: str) -> None:
        self.require_owner(by)
        email_clean = email.strip().lower()
        if email_clean == self.owner_email.lower():
            raise Invalid("cannot remove board owner")
        if email_clean not in self.members:
            raise Invalid(f"{email_clean} is not a member of this board")
        del self.members[email_clean]
