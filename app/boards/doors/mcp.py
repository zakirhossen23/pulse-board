"""The MCP door: the same use cases as the web routes, as tools Claude or ChatGPT can call.

Each tool acts as the person who connected (their gateway identity), so an agent sees exactly
the boards its person sees. Tools are actions, never raw table access.
"""
from typing import List, Optional
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from boards.application.use_cases import Boards, NotFound
from boards.doors.identity import person_from
from boards.domain.model import Forbidden, Invalid

INSTRUCTIONS = (
    "PulseBoard: A collaborative team task board. Lists are 'To do', 'Doing', and 'Done'. "
    "Use my_boards to find accessible boards. "
    "Use show_board to see all lists, cards, and members on a board. "
    "Use my_cards to see tasks assigned to you ('what's on my plate this week?'). "
    "Use list_overdue to see past-due items ('what's overdue?'). "
    "Use add_card, move_card, assign_card, and update_card to manage cards. "
    "Use what_is_blocking to inspect card dependencies. "
    "Use suggest_checklist, board_summary, and find_similar_cards for AI insights."
)


def build_mcp(boards: Boards) -> MCPServer:
    server = MCPServer(name="pulse-boards", instructions=INSTRUCTIONS)

    def call(ctx: Context, fn, *args, **kwargs):
        person = person_from(ctx.headers or {})
        if person is None:
            raise ToolError("401: sign in first")
        try:
            return fn(person, *args, **kwargs)
        except (NotFound, Forbidden, Invalid) as e:
            raise ToolError(str(e))

    @server.tool()
    def my_boards(ctx: Context) -> list:
        """The boards you are on, with your role on each (owner, member, or viewer)."""
        return call(ctx, boards.my_boards)

    @server.tool()
    def show_board(board_id: str, ctx: Context) -> dict:
        """A board, all its members, and all its cards grouped with due dates and labels."""
        return call(ctx, boards.show_board, board_id)

    @server.tool()
    def create_board(title: str, ctx: Context) -> dict:
        """Create a new board. You become its owner."""
        return call(ctx, boards.create_board, title)

    @server.tool()
    def add_card(board_id: str, title: str, ctx: Context,
                 list_name: str = "To do", description: str = "",
                 assignee: Optional[str] = None, due_date: Optional[str] = None,
                 labels: Optional[List[str]] = None,
                 blocked_by: Optional[List[str]] = None) -> dict:
        """Add a card to a list on a board. Optional assignee (email), due_date (YYYY-MM-DD), labels, and blocked_by IDs."""
        return call(ctx, boards.add_card, board_id, title, list_name=list_name,
                    description=description, assignee=assignee, due_date=due_date,
                    labels=labels, blocked_by=blocked_by)

    @server.tool()
    def move_card(card_id: str, list_name: str, ctx: Context) -> dict:
        """Move a card to 'To do', 'Doing', or 'Done'."""
        return call(ctx, boards.move_card, card_id, list_name)

    @server.tool()
    def assign_card(card_id: str, ctx: Context, email: Optional[str] = None) -> dict:
        """Assign or unassign a card to a team member by email."""
        return call(ctx, boards.assign_card, card_id, email)

    @server.tool()
    def update_card(card_id: str, ctx: Context,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    assignee: Optional[str] = None,
                    due_date: Optional[str] = None,
                    labels: Optional[List[str]] = None,
                    blocked_by: Optional[List[str]] = None) -> dict:
        """Update any attributes of a card: title, description, assignee, due_date, labels, or blocked_by card IDs."""
        return call(ctx, boards.update_card, card_id, title=title, description=description,
                    assignee=assignee, due_date=due_date, labels=labels, blocked_by=blocked_by)

    @server.tool()
    def delete_card(card_id: str, ctx: Context) -> dict:
        """Delete a card from its board."""
        return call(ctx, boards.delete_card, card_id)

    @server.tool()
    def my_cards(ctx: Context, only_due_this_week: bool = False) -> list:
        """What's on my plate: returns all cards assigned to you across accessible boards. Set only_due_this_week=True to filter for the coming 7 days."""
        return call(ctx, boards.list_my_cards, only_due_this_week=only_due_this_week)

    @server.tool()
    def list_overdue(ctx: Context, board_id: Optional[str] = None) -> list:
        """What's overdue: returns cards past their due date that are not in 'Done'."""
        return call(ctx, boards.list_overdue, board_id=board_id)

    @server.tool()
    def what_is_blocking(ctx: Context, card_id: Optional[str] = None,
                         board_id: Optional[str] = None) -> dict:
        """Dependencies check: inspect blockers for a specific card or find all blocked cards across a board."""
        return call(ctx, boards.what_is_blocking, card_id=card_id, board_id=board_id)

    @server.tool()
    def card_history(card_id: str, ctx: Context) -> list:
        """Every change recorded for a card: who, when, what changed."""
        return call(ctx, boards.card_history, card_id)

    @server.tool()
    def board_history(board_id: str, ctx: Context) -> list:
        """Recent activity log for the entire board."""
        return call(ctx, boards.board_history, board_id)

    @server.tool()
    def add_member(board_id: str, email: str, ctx: Context, role: str = "member") -> dict:
        """Owner only: invite or update someone on a board as 'member' or 'viewer'."""
        return call(ctx, boards.add_member, board_id, email, role)

    @server.tool()
    def remove_member(board_id: str, email: str, ctx: Context) -> dict:
        """Owner only: remove someone from a board."""
        return call(ctx, boards.remove_member, board_id, email)

    @server.tool()
    def suggest_checklist(card_id: str, ctx: Context) -> dict:
        """AI suggestion of actionable checklist steps for a card."""
        return call(ctx, boards.suggest_checklist, card_id)

    @server.tool()
    def board_summary(board_id: str, ctx: Context) -> dict:
        """AI daily standup summary of board progress, in-flight work, and overdue risks."""
        return call(ctx, boards.board_summary, board_id)

    @server.tool()
    def find_similar_cards(card_id: str, ctx: Context) -> dict:
        """AI search for related or overlapping cards on the same board."""
        return call(ctx, boards.find_similar_cards, card_id)

    return server
