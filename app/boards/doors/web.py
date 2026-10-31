"""The web door: JSON routes plus a responsive, feature-rich Kanban web UI.
Every route calls a use case and nothing else.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from boards.application.use_cases import Boards, NotFound
from boards.doors.identity import person_from
from boards.domain.model import Forbidden, Invalid, Person


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

    @r.get("/", response_class=HTMLResponse)
    def page(request: Request):
        if person_from(request.headers) is None:
            return RedirectResponse("/.dodil/auth/login?return_to=/", status_code=303)
        return PAGE

    return r


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PulseBoard - Team Kanban</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .card-drag-over { border: 2px dashed #6366f1 !important; background: #eef2ff !important; }
    .col-drag-over { background: #e0e7ff !important; }
    .grabbing { cursor: grabbing !important; }
  </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans antialiased min-h-screen flex flex-col">

  <!-- Header -->
  <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white font-black text-lg shadow-md shadow-indigo-100">
          ⚡
        </div>
        <div>
          <span class="font-extrabold text-lg tracking-tight bg-gradient-to-r from-indigo-700 to-violet-600 bg-clip-text text-transparent">PulseBoard</span>
          <span class="hidden sm:inline-block text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full ml-1 font-medium">Team Task Board</span>
        </div>
      </div>

      <!-- Board selector & actions -->
      <div class="flex items-center gap-2">
        <select id="boardSelect" onchange="switchBoard(this.value)" class="bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 max-w-xs">
          <option value="">Loading boards...</option>
        </select>
        <button onclick="openModal('newBoardModal')" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1 transition shadow-sm">
          <span>+</span> <span class="hidden sm:inline">New Board</span>
        </button>
      </div>

      <!-- Right menu: User identity & logout -->
      <div class="flex items-center gap-3">
        <div class="text-right hidden md:block">
          <div id="userEmail" class="text-xs font-semibold text-slate-700">user@example.com</div>
          <div id="userRoleBadge" class="text-[10px] text-indigo-600 font-bold uppercase tracking-wider">Member</div>
        </div>
        <a href="/.dodil/auth/logout" class="text-xs text-slate-700 hover:text-red-600 font-medium px-2 py-1 rounded hover:bg-slate-100 transition">
          Sign out
        </a>
      </div>
    </div>

    <!-- Sub-bar: Board controls & filters -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-sm">
      <div class="flex items-center gap-2 flex-wrap">
        <button onclick="openMembersModal()" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition">
          👥 <span id="membersBtnLabel">Members</span>
        </button>
        <button onclick="openBoardHistoryModal()" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition">
          📜 Activity Log
        </button>
        <button onclick="generateBoardSummary()" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-violet-50 hover:bg-violet-100 text-violet-700 border border-violet-200 transition">
          ✨ Daily AI Summary
        </button>
        <button onclick="showMyCards()" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 transition">
          📌 My Plate
        </button>
      </div>

      <!-- Filter search & overdue toggle -->
      <div class="flex items-center gap-2">
        <input id="searchInput" type="text" placeholder="Filter cards..." oninput="applyFilter()" class="bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-36 sm:w-48">
        <label class="flex items-center gap-1 text-xs text-slate-600 cursor-pointer select-none">
          <input type="checkbox" id="overdueOnlyToggle" onchange="applyFilter()" class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500">
          <span class="font-medium">Overdue only</span>
        </label>
      </div>
    </div>
  </header>

  <!-- Main Board Canvas -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 overflow-x-auto">
    <div id="boardTitleContainer" class="mb-4 flex items-center justify-between">
      <div>
        <h1 id="currentBoardTitle" class="text-2xl font-black text-slate-800 tracking-tight">Board</h1>
        <p id="boardSubtext" class="text-xs text-slate-600">Select or create a board to get started</p>
      </div>
      <div id="roleWarningBanner" class="hidden text-xs bg-amber-100 text-amber-800 px-3 py-1.5 rounded-lg border border-amber-200 font-medium">
        👀 You are viewing this board as a <b>Viewer</b> (read-only mode).
      </div>
    </div>

    <!-- Columns Container -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">

      <!-- Column: To do -->
      <div class="bg-slate-200/70 rounded-2xl p-4 flex flex-col max-h-[80vh] border border-slate-300/60 shadow-sm transition-colors duration-150"
           id="col-To-do" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event, 'To do')">
        <div class="flex items-center justify-between mb-3 px-1">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
            <h2 class="font-bold text-sm text-slate-700 tracking-wide uppercase">To do</h2>
          </div>
          <span id="count-To-do" class="bg-slate-300 text-slate-700 text-xs font-semibold px-2 py-0.5 rounded-full">0</span>
        </div>
        <div id="cards-To-do" class="flex-1 overflow-y-auto space-y-3 min-h-[50px] p-0.5"></div>
        <div class="mt-3 pt-2 border-t border-slate-300/50">
          <form onsubmit="quickAddCard(event, 'To do')" class="can-edit">
            <div class="flex gap-1.5">
              <input name="cardTitle" placeholder="+ Add a card..." required class="flex-1 bg-white border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <button class="bg-slate-700 hover:bg-slate-800 text-white text-xs px-2.5 py-1.5 rounded-lg font-medium transition">Add</button>
            </div>
          </form>
        </div>
      </div>

      <!-- Column: Doing -->
      <div class="bg-slate-200/70 rounded-2xl p-4 flex flex-col max-h-[80vh] border border-slate-300/60 shadow-sm transition-colors duration-150"
           id="col-Doing" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event, 'Doing')">
        <div class="flex items-center justify-between mb-3 px-1">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
            <h2 class="font-bold text-sm text-slate-700 tracking-wide uppercase">Doing</h2>
          </div>
          <span id="count-Doing" class="bg-amber-200 text-amber-800 text-xs font-semibold px-2 py-0.5 rounded-full">0</span>
        </div>
        <div id="cards-Doing" class="flex-1 overflow-y-auto space-y-3 min-h-[50px] p-0.5"></div>
        <div class="mt-3 pt-2 border-t border-slate-300/50">
          <form onsubmit="quickAddCard(event, 'Doing')" class="can-edit">
            <div class="flex gap-1.5">
              <input name="cardTitle" placeholder="+ Add a card..." required class="flex-1 bg-white border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <button class="bg-amber-600 hover:bg-amber-700 text-white text-xs px-2.5 py-1.5 rounded-lg font-medium transition">Add</button>
            </div>
          </form>
        </div>
      </div>

      <!-- Column: Done -->
      <div class="bg-slate-200/70 rounded-2xl p-4 flex flex-col max-h-[80vh] border border-slate-300/60 shadow-sm transition-colors duration-150"
           id="col-Done" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event, 'Done')">
        <div class="flex items-center justify-between mb-3 px-1">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            <h2 class="font-bold text-sm text-slate-700 tracking-wide uppercase">Done</h2>
          </div>
          <span id="count-Done" class="bg-emerald-200 text-emerald-800 text-xs font-semibold px-2 py-0.5 rounded-full">0</span>
        </div>
        <div id="cards-Done" class="flex-1 overflow-y-auto space-y-3 min-h-[50px] p-0.5"></div>
        <div class="mt-3 pt-2 border-t border-slate-300/50">
          <form onsubmit="quickAddCard(event, 'Done')" class="can-edit">
            <div class="flex gap-1.5">
              <input name="cardTitle" placeholder="+ Add a card..." required class="flex-1 bg-white border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <button class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs px-2.5 py-1.5 rounded-lg font-medium transition">Add</button>
            </div>
          </form>
        </div>
      </div>

    </div>
  </main>

  <!-- Card Detail Modal -->
  <div id="cardModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
    <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full p-6 relative border border-slate-200 max-h-[90vh] flex flex-col">
      <button onclick="closeModal('cardModal')" class="absolute top-4 right-4 text-slate-400 hover:text-slate-600 text-xl font-bold">✕</button>

      <div class="flex items-center gap-2 mb-2">
        <span id="modalListBadge" class="text-xs px-2.5 py-0.5 rounded-full font-bold bg-slate-100 text-slate-700">To do</span>
        <span id="modalOverdueBadge" class="hidden text-xs px-2 py-0.5 rounded-full font-bold bg-rose-100 text-rose-700">⚠️ Overdue</span>
        <span id="modalBlockedBadge" class="hidden text-xs px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800">🚫 Blocked</span>
      </div>

      <div class="flex-1 overflow-y-auto pr-1 space-y-4">
        <!-- Title & Status -->
        <div>
          <label class="text-xs font-bold text-slate-400 uppercase tracking-wider">Card Title</label>
          <input id="modalTitle" class="w-full text-lg font-bold text-slate-800 border-b border-transparent hover:border-slate-300 focus:border-indigo-500 focus:outline-none py-1">
        </div>

        <!-- Meta row: Assignee & Due Date -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">Assignee</label>
            <select id="modalAssignee" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500">
              <option value="">Unassigned</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">Due Date</label>
            <input id="modalDueDate" type="date" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500">
          </div>
        </div>

        <!-- Labels / Tags -->
        <div>
          <label class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">Labels (comma separated)</label>
          <input id="modalLabels" placeholder="e.g. backend, urgent, v1" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500">
        </div>

        <!-- Description -->
        <div>
          <label class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-1">Description & Notes</label>
          <textarea id="modalDesc" rows="4" placeholder="Add detailed notes or requirements..." class="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500 font-mono"></textarea>
        </div>

        <!-- Card Dependencies (Blocked By) -->
        <div class="bg-slate-50 p-3 rounded-xl border border-slate-200">
          <div class="flex items-center justify-between mb-2">
            <label class="text-xs font-bold text-slate-600 uppercase tracking-wider">Blocked By (Dependencies)</label>
          </div>
          <p class="text-[11px] text-slate-500 mb-2">Select cards that must be completed before this card can finish:</p>
          <select id="modalBlockersSelect" multiple size="3" class="w-full bg-white border border-slate-200 rounded-lg p-2 text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500">
          </select>
          <div id="modalBlockersStatus" class="mt-2 space-y-1"></div>
        </div>

        <!-- AI Assistant Powerups -->
        <div class="bg-indigo-50/60 border border-indigo-100 rounded-xl p-3.5 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-indigo-900 flex items-center gap-1.5">
              ✨ AI Powerups (Dodil Models)
            </span>
          </div>
          <div class="flex flex-wrap gap-2">
            <button onclick="aiGenerateChecklist()" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition shadow-sm">
              Generate Checklist Steps
            </button>
            <button onclick="aiFindSimilarCards()" class="bg-white hover:bg-slate-50 text-indigo-700 border border-indigo-200 text-xs font-medium px-3 py-1.5 rounded-lg transition">
              Find Similar / Duplicate Cards
            </button>
          </div>
          <div id="aiOutputBox" class="hidden text-xs bg-white border border-indigo-200 rounded-lg p-3 text-slate-700 whitespace-pre-wrap max-h-40 overflow-y-auto"></div>
        </div>

        <!-- Activity History Timeline -->
        <div>
          <label class="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">Card History</label>
          <div id="cardHistoryTimeline" class="space-y-2 max-h-44 overflow-y-auto pr-1 text-xs">
            <div class="text-slate-400 italic">No history recorded yet.</div>
          </div>
        </div>
      </div>

      <!-- Footer Buttons -->
      <div class="pt-4 mt-2 border-t border-slate-100 flex items-center justify-between">
        <button onclick="deleteCurrentCard()" class="text-rose-600 hover:text-rose-700 text-xs font-bold px-3 py-1.5 rounded hover:bg-rose-50 transition can-edit">
          Delete Card
        </button>
        <div class="flex items-center gap-2">
          <button onclick="closeModal('cardModal')" class="text-slate-500 hover:text-slate-700 text-xs font-medium px-4 py-2 rounded-lg">Cancel</button>
          <button onclick="saveCardDetails()" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2 rounded-lg transition shadow-sm can-edit">
            Save Changes
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- New Board Modal -->
  <div id="newBoardModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 border border-slate-200">
      <h3 class="font-extrabold text-base text-slate-800 mb-2">Create New Board</h3>
      <p class="text-xs text-slate-500 mb-4">You will be designated as the owner of this board.</p>
      <form onsubmit="handleCreateBoard(event)">
        <input id="newBoardTitleInput" placeholder="e.g. Q4 Product Launch" required class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 mb-4 focus:ring-2 focus:ring-indigo-500">
        <div class="flex justify-end gap-2">
          <button type="button" onclick="closeModal('newBoardModal')" class="text-xs px-3 py-2 text-slate-500">Cancel</button>
          <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2 rounded-lg transition">Create Board</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Members Management Modal -->
  <div id="membersModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 border border-slate-200">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-extrabold text-base text-slate-800">Board Members</h3>
        <button onclick="closeModal('membersModal')" class="text-slate-400 hover:text-slate-600">✕</button>
      </div>
      <p class="text-xs text-slate-500 mb-4">Owner can invite members or viewers. Viewers have read-only access.</p>

      <div id="membersList" class="space-y-2 mb-4 max-h-48 overflow-y-auto"></div>

      <form id="inviteMemberForm" onsubmit="handleInviteMember(event)" class="pt-3 border-t border-slate-100 flex flex-col gap-2">
        <label class="text-xs font-bold text-slate-500">Invite New Person</label>
        <div class="flex gap-2">
          <input id="inviteEmail" type="email" placeholder="colleague@example.com" required class="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs">
          <select id="inviteRole" class="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-medium">
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>
        <button class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-2 rounded-lg transition">
          Add Member
        </button>
      </form>
    </div>
  </div>

  <!-- Activity Log Modal -->
  <div id="activityModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6 border border-slate-200">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-extrabold text-base text-slate-800">Board Activity Feed</h3>
        <button onclick="closeModal('activityModal')" class="text-slate-400 hover:text-slate-600">✕</button>
      </div>
      <div id="boardActivityTimeline" class="space-y-3 max-h-96 overflow-y-auto pr-1 text-xs"></div>
    </div>
  </div>

  <!-- AI Summary Modal -->
  <div id="summaryModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6 border border-slate-200">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-extrabold text-base text-violet-900 flex items-center gap-1.5">
          ✨ AI Daily Standup Summary
        </h3>
        <button onclick="closeModal('summaryModal')" class="text-slate-400 hover:text-slate-600">✕</button>
      </div>
      <div id="summaryContent" class="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto bg-violet-50/50 p-4 rounded-xl border border-violet-100">
        Generating summary via Dodil Models...
      </div>
    </div>
  </div>

  <!-- My Plate Modal -->
  <div id="myPlateModal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6 border border-slate-200">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-extrabold text-base text-slate-800 flex items-center gap-1.5">
          📌 What's on My Plate
        </h3>
        <button onclick="closeModal('myPlateModal')" class="text-slate-400 hover:text-slate-600">✕</button>
      </div>
      <div class="mb-3 flex gap-2">
        <button onclick="loadMyPlate(false)" class="text-xs px-2.5 py-1 bg-slate-100 rounded font-medium">All My Tasks</button>
        <button onclick="loadMyPlate(true)" class="text-xs px-2.5 py-1 bg-amber-100 text-amber-800 rounded font-medium">Due This Week</button>
      </div>
      <div id="myPlateList" class="space-y-2 max-h-80 overflow-y-auto text-xs"></div>
    </div>
  </div>

  <!-- Frontend Logic -->
  <script>
    let currentBoard = null;
    let currentCardId = null;
    let allCards = [];
    let currentUser = null;
    let draggedCardId = null;

    const j = (url, opts = {}) => fetch(url, {
      headers: { 'content-type': 'application/json' },
      ...opts
    }).then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
      return data;
    });

    async function init() {
      try {
        const me = await j('/api/me');
        currentUser = me.email;
        document.getElementById('userEmail').innerText = me.email || 'Anonymous';
      } catch (err) {}
      await loadBoards();
    }

    async function loadBoards() {
      const boards = await j('/api/boards');
      const sel = document.getElementById('boardSelect');
      sel.innerHTML = '';
      if (!boards || boards.length === 0) {
        sel.innerHTML = '<option value="">No boards found</option>';
        document.getElementById('currentBoardTitle').innerText = 'No boards yet';
        document.getElementById('boardSubtext').innerText = 'Click "+ New Board" above to create your first board.';
        return;
      }
      boards.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = `${b.title} (${b.role})`;
        sel.appendChild(opt);
      });
      if (!currentBoard || !boards.some(b => b.id === currentBoard.id)) {
        await switchBoard(boards[0].id);
      } else {
        await switchBoard(currentBoard.id);
      }
    }

    async function switchBoard(boardId) {
      if (!boardId) return;
      currentBoard = await j(`/api/boards/${boardId}`);
      document.getElementById('boardSelect').value = boardId;
      document.getElementById('currentBoardTitle').innerText = currentBoard.title;
      document.getElementById('userRoleBadge').innerText = currentBoard.role;
      document.getElementById('boardSubtext').innerText = `Owner: ${currentBoard.owner_email}`;
      document.getElementById('membersBtnLabel').innerText = `Members (${(currentBoard.members || []).length})`;

      const isViewer = currentBoard.role === 'viewer';
      document.getElementById('roleWarningBanner').classList.toggle('hidden', !isViewer);
      document.querySelectorAll('.can-edit').forEach(el => {
        el.style.display = isViewer ? 'none' : '';
      });

      allCards = currentBoard.cards || [];
      renderBoard();
    }

    function renderBoard(cards = allCards) {
      ['To do', 'Doing', 'Done'].forEach(list => {
        const listCards = cards.filter(c => c.list_name === list);
        const container = document.getElementById(`cards-${list.replace(' ', '-')}`);
        const countBadge = document.getElementById(`count-${list.replace(' ', '-')}`);
        countBadge.innerText = listCards.length;
        container.innerHTML = '';

        listCards.forEach(c => {
          const cardEl = document.createElement('div');
          cardEl.className = 'bg-white rounded-xl p-3 shadow-sm border border-slate-200/80 hover:shadow-md transition cursor-pointer select-none';
          cardEl.draggable = currentBoard.role !== 'viewer';
          cardEl.ondragstart = (e) => handleDragStart(e, c.id);
          cardEl.onclick = () => openCardDetails(c.id);

          // Labels
          let labelsHtml = '';
          if (c.labels && c.labels.length) {
            labelsHtml = `<div class="flex flex-wrap gap-1 mb-1.5">` +
              c.labels.map(l => `<span class="bg-indigo-50 text-indigo-700 text-[10px] font-semibold px-2 py-0.5 rounded-full">${escapeHtml(l)}</span>`).join('') +
              `</div>`;
          }

          // Indicators: overdue, blockers, assignee
          let metaHtml = '<div class="flex items-center justify-between mt-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">';
          let flags = [];
          if (c.is_overdue) {
            flags.push('<span class="text-rose-600 font-bold bg-rose-50 px-1.5 py-0.5 rounded">⚠️ Overdue</span>');
          } else if (c.due_date) {
            flags.push(`<span>📅 ${c.due_date}</span>`);
          }
          if (c.blocked_by && c.blocked_by.length) {
            flags.push('<span class="text-amber-700 font-bold bg-amber-50 px-1.5 py-0.5 rounded">🚫 Blocked</span>');
          }
          metaHtml += `<div>${flags.join(' ')}</div>`;

          if (c.assignee) {
            const shortName = c.assignee.split('@')[0];
            metaHtml += `<span class="bg-slate-100 text-slate-700 font-medium px-1.5 py-0.5 rounded text-[10px]" title="${c.assignee}">👤 ${escapeHtml(shortName)}</span>`;
          } else {
            metaHtml += `<span class="text-slate-300 text-[10px]">&mdash;</span>`;
          }
          metaHtml += '</div>';

          cardEl.innerHTML = labelsHtml + `<div class="font-semibold text-xs text-slate-800 leading-snug">${escapeHtml(c.title)}</div>` + metaHtml;
          container.appendChild(cardEl);
        });
      });
    }

    function applyFilter() {
      const q = document.getElementById('searchInput').value.toLowerCase().trim();
      const overdueOnly = document.getElementById('overdueOnlyToggle').checked;
      const filtered = allCards.filter(c => {
        if (overdueOnly && !c.is_overdue) return false;
        if (!q) return true;
        const inTitle = (c.title || '').toLowerCase().includes(q);
        const inDesc = (c.description || '').toLowerCase().includes(q);
        const inAssignee = (c.assignee || '').toLowerCase().includes(q);
        const inLabels = (c.labels || []).some(l => l.toLowerCase().includes(q));
        return inTitle || inDesc || inAssignee || inLabels;
      });
      renderBoard(filtered);
    }

    /* Drag and drop */
    function handleDragStart(e, cardId) {
      draggedCardId = cardId;
      e.dataTransfer.setData('text/plain', cardId);
      e.target.classList.add('grabbing');
    }
    function handleDragOver(e) {
      e.preventDefault();
      e.currentTarget.classList.add('col-drag-over');
    }
    function handleDragLeave(e) {
      e.currentTarget.classList.remove('col-drag-over');
    }
    async function handleDrop(e, targetList) {
      e.preventDefault();
      e.currentTarget.classList.remove('col-drag-over');
      const cardId = draggedCardId || e.dataTransfer.getData('text/plain');
      if (!cardId) return;
      try {
        await j(`/api/cards/${cardId}/move`, { method: 'POST', body: JSON.stringify({ list_name: targetList }) });
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    /* Quick add card */
    async function quickAddCard(e, listName) {
      e.preventDefault();
      const input = e.target.cardTitle;
      const title = input.value.trim();
      if (!title) return;
      try {
        await j(`/api/boards/${currentBoard.id}/cards`, {
          method: 'POST',
          body: JSON.stringify({ title, list_name: listName })
        });
        input.value = '';
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    /* Card Details Modal */
    async function openCardDetails(cardId) {
      currentCardId = cardId;
      const card = allCards.find(c => c.id === cardId);
      if (!card) return;

      document.getElementById('modalTitle').value = card.title;
      document.getElementById('modalListBadge').innerText = card.list_name;
      document.getElementById('modalDesc').value = card.description || '';
      document.getElementById('modalDueDate').value = card.due_date || '';
      document.getElementById('modalLabels').value = (card.labels || []).join(', ');

      document.getElementById('modalOverdueBadge').classList.toggle('hidden', !card.is_overdue);

      // Populate assignees
      const assSelect = document.getElementById('modalAssignee');
      assSelect.innerHTML = '<option value="">Unassigned</option>';
      (currentBoard.members || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.email;
        opt.textContent = `${m.email} (${m.role})`;
        if (card.assignee && card.assignee.toLowerCase() === m.email.toLowerCase()) opt.selected = true;
        assSelect.appendChild(opt);
      });

      // Populate blockers
      const blockSelect = document.getElementById('modalBlockersSelect');
      blockSelect.innerHTML = '';
      allCards.filter(c => c.id !== card.id).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `[${c.list_name}] ${c.title}`;
        if ((card.blocked_by || []).includes(c.id)) opt.selected = true;
        blockSelect.appendChild(opt);
      });

      // Fetch blockers info
      try {
        const blockingInfo = await j(`/api/cards/${card.id}/blocking`);
        document.getElementById('modalBlockedBadge').classList.toggle('hidden', !blockingInfo.is_blocked);
        const statusBox = document.getElementById('modalBlockersStatus');
        if (blockingInfo.blockers && blockingInfo.blockers.length) {
          statusBox.innerHTML = blockingInfo.blockers.map(b =>
            `<div class="text-[11px] ${b.is_done ? 'text-emerald-600' : 'text-amber-600 font-semibold'}">
              ${b.is_done ? '✓' : '⚠️'} [${b.list_name}] ${escapeHtml(b.title)} (${b.assignee || 'unassigned'})
            </div>`
          ).join('');
        } else {
          statusBox.innerHTML = '<div class="text-[11px] text-slate-400">No dependencies linked.</div>';
        }
      } catch (err) {}

      // Fetch card history
      try {
        const history = await j(`/api/cards/${card.id}/history`);
        const timeline = document.getElementById('cardHistoryTimeline');
        if (!history || history.length === 0) {
          timeline.innerHTML = '<div class="text-slate-400 italic">No activity recorded yet.</div>';
        } else {
          timeline.innerHTML = history.map(h => `
            <div class="flex items-start gap-2 bg-slate-50 p-2 rounded-lg border border-slate-100">
              <span class="text-slate-400 font-mono text-[10px] whitespace-nowrap">${h.event_at ? h.event_at.replace('T', ' ').substring(0, 16) : ''}</span>
              <div>
                <span class="font-bold text-slate-700">${escapeHtml(h.actor)}</span>:
                <span class="text-slate-600">${escapeHtml(h.action)}</span>
              </div>
            </div>
          `).join('');
        }
      } catch (err) {}

      document.getElementById('aiOutputBox').classList.add('hidden');
      openModal('cardModal');
    }

    async function saveCardDetails() {
      if (!currentCardId) return;
      const title = document.getElementById('modalTitle').value.trim();
      const description = document.getElementById('modalDesc').value;
      const assignee = document.getElementById('modalAssignee').value;
      const due_date = document.getElementById('modalDueDate').value;
      const labels = document.getElementById('modalLabels').value.split(',').map(s => s.trim()).filter(Boolean);

      const blockSelect = document.getElementById('modalBlockersSelect');
      const blocked_by = Array.from(blockSelect.selectedOptions).map(opt => opt.value);

      try {
        await j(`/api/cards/${currentCardId}`, {
          method: 'PATCH',
          body: JSON.stringify({ title, description, assignee, due_date, labels, blocked_by })
        });
        closeModal('cardModal');
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    async function deleteCurrentCard() {
      if (!currentCardId) return;
      if (!confirm('Are you sure you want to delete this card?')) return;
      try {
        await j(`/api/cards/${currentCardId}`, { method: 'DELETE' });
        closeModal('cardModal');
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    /* AI Tools */
    async function aiGenerateChecklist() {
      if (!currentCardId) return;
      const box = document.getElementById('aiOutputBox');
      box.classList.remove('hidden');
      box.innerText = 'Calling Dodil Models (kimi-k2.6) for checklist steps...';
      try {
        const res = await j(`/api/cards/${currentCardId}/checklist`, { method: 'POST' });
        const steps = res.suggested_checklist || [];
        box.innerText = "Suggested Checklist:\n" + steps.map(s => `[ ] ${s}`).join('\n') + "\n\n(Click 'Append to Description' to save)";
        const appendBtn = document.createElement('button');
        appendBtn.className = "mt-2 bg-indigo-600 text-white text-xs px-2.5 py-1 rounded font-semibold block";
        appendBtn.textContent = "Append to Description";
        appendBtn.onclick = () => {
          const desc = document.getElementById('modalDesc');
          desc.value = (desc.value.trim() ? desc.value.trim() + '\n\n### Checklist\n' : '### Checklist\n') + steps.map(s => `- [ ] ${s}`).join('\n');
          appendBtn.remove();
        };
        box.appendChild(appendBtn);
      } catch (err) {
        box.innerText = 'AI error: ' + err.message;
      }
    }

    async function aiFindSimilarCards() {
      if (!currentCardId) return;
      const box = document.getElementById('aiOutputBox');
      box.classList.remove('hidden');
      box.innerText = 'Searching for related cards on this board...';
      try {
        const res = await j(`/api/cards/${currentCardId}/similar`);
        const matches = res.similar_cards || [];
        if (!matches.length) {
          box.innerText = 'No similar cards found on this board.';
        } else {
          box.innerText = "Related Cards Found:\n\n" + matches.map(m => `• ${m.title} (${m.reason || 'Related task'})`).join('\n\n');
        }
      } catch (err) {
        box.innerText = 'Error: ' + err.message;
      }
    }

    async function generateBoardSummary() {
      if (!currentBoard) return;
      openModal('summaryModal');
      document.getElementById('summaryContent').innerText = 'Generating daily standup summary via Dodil Models...';
      try {
        const res = await j(`/api/boards/${currentBoard.id}/summary`);
        document.getElementById('summaryContent').innerText = res.summary;
      } catch (err) {
        document.getElementById('summaryContent').innerText = 'AI summary failed: ' + err.message;
      }
    }

    /* Board Creation */
    async function handleCreateBoard(e) {
      e.preventDefault();
      const title = document.getElementById('newBoardTitleInput').value.trim();
      if (!title) return;
      try {
        const b = await j('/api/boards', { method: 'POST', body: JSON.stringify({ title }) });
        closeModal('newBoardModal');
        await loadBoards();
        await switchBoard(b.id);
      } catch (err) {
        alert(err.message);
      }
    }

    /* Members Management */
    function openMembersModal() {
      if (!currentBoard) return;
      const list = document.getElementById('membersList');
      list.innerHTML = (currentBoard.members || []).map(m => `
        <div class="flex items-center justify-between bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-xs">
          <div>
            <span class="font-bold text-slate-800">${escapeHtml(m.email)}</span>
            <span class="ml-2 font-semibold uppercase text-[10px] px-1.5 py-0.5 rounded ${m.role === 'owner' ? 'bg-indigo-100 text-indigo-700' : m.role === 'member' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-700'}">${m.role}</span>
          </div>
          ${currentBoard.role === 'owner' && m.role !== 'owner' ? `
            <button onclick="removeMember('${m.email}')" class="text-rose-600 hover:text-rose-800 font-bold">Remove</button>
          ` : ''}
        </div>
      `).join('');

      document.getElementById('inviteMemberForm').style.display = currentBoard.role === 'owner' ? '' : 'none';
      openModal('membersModal');
    }

    async function handleInviteMember(e) {
      e.preventDefault();
      const email = document.getElementById('inviteEmail').value.trim();
      const role = document.getElementById('inviteRole').value;
      try {
        await j(`/api/boards/${currentBoard.id}/members`, {
          method: 'POST',
          body: JSON.stringify({ email, role })
        });
        document.getElementById('inviteEmail').value = '';
        closeModal('membersModal');
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    async function removeMember(email) {
      if (!confirm(`Remove ${email} from this board?`)) return;
      try {
        await j(`/api/boards/${currentBoard.id}/members/${encodeURIComponent(email)}`, { method: 'DELETE' });
        closeModal('membersModal');
        await switchBoard(currentBoard.id);
      } catch (err) {
        alert(err.message);
      }
    }

    /* Board History */
    async function openBoardHistoryModal() {
      if (!currentBoard) return;
      openModal('activityModal');
      const box = document.getElementById('boardActivityTimeline');
      box.innerHTML = 'Loading feed...';
      try {
        const acts = await j(`/api/boards/${currentBoard.id}/activity`);
        if (!acts || !acts.length) {
          box.innerHTML = '<div class="text-slate-400 italic">No activity yet.</div>';
          return;
        }
        box.innerHTML = acts.map(a => `
          <div class="flex items-start gap-2 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
            <span class="text-slate-400 font-mono text-[10px] whitespace-nowrap">${a.event_at ? a.event_at.replace('T', ' ').substring(0, 16) : ''}</span>
            <div>
              <span class="font-bold text-slate-700">${escapeHtml(a.actor)}</span>:
              <span class="text-slate-600">${escapeHtml(a.action)}</span>
            </div>
          </div>
        `).join('');
      } catch (err) {
        box.innerHTML = 'Failed to load activity.';
      }
    }

    /* My Plate */
    async function showMyCards() {
      openModal('myPlateModal');
      await loadMyPlate(false);
    }
    async function loadMyPlate(thisWeek) {
      const box = document.getElementById('myPlateList');
      box.innerHTML = 'Loading your assigned cards...';
      try {
        const cards = await j(`/api/cards/my?this_week=${thisWeek}`);
        if (!cards || !cards.length) {
          box.innerHTML = '<div class="text-slate-400 italic">No tasks assigned to you.</div>';
          return;
        }
        box.innerHTML = cards.map(c => `
          <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-200 flex items-center justify-between cursor-pointer hover:bg-slate-100 transition" onclick="closeModal('myPlateModal'); switchBoard('${c.board_id}').then(() => openCardDetails('${c.id}'))">
            <div>
              <span class="text-[10px] font-bold text-indigo-600 uppercase tracking-wider block">${escapeHtml(c.board_title || 'Board')} &bull; ${c.list_name}</span>
              <span class="font-semibold text-slate-800">${escapeHtml(c.title)}</span>
            </div>
            <div class="text-right">
              ${c.is_overdue ? '<span class="text-rose-600 font-bold bg-rose-50 px-1.5 py-0.5 rounded text-[10px]">⚠️ Overdue</span>' : c.due_date ? `<span class="text-slate-500 text-[10px]">Due ${c.due_date}</span>` : ''}
            </div>
          </div>
        `).join('');
      } catch (err) {
        box.innerHTML = 'Failed to load cards: ' + err.message;
      }
    }

    /* Modal utils */
    function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
    function closeModal(id) { document.getElementById(id).classList.add('hidden'); }
    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/[&<>"']/g, m => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[m]);
    }

    init();
  </script>
</body>
</html>
"""
