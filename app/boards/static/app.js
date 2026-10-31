// PulseBoard Client Application
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
        labelsHtml = '<div class="flex flex-wrap gap-1 mb-1.5">' +
          c.labels.map(l => `<span class="bg-indigo-50 text-indigo-700 text-[10px] font-semibold px-2 py-0.5 rounded-full">${escapeHtml(l)}</span>`).join('') +
          '</div>';
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
        metaHtml += '<span class="text-slate-300 text-[10px]">&mdash;</span>';
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

  switchDescTab('write');

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
  document.getElementById('summaryContent').innerHTML = '<div class="text-violet-600 font-medium animate-pulse">Generating daily standup summary via Dodil Models (kimi-k2.6)...</div>';
  try {
    const res = await j(`/api/boards/${currentBoard.id}/summary`);
    document.getElementById('summaryContent').innerHTML = renderMarkdown(res.summary);
  } catch (err) {
    document.getElementById('summaryContent').innerHTML = '<div class="text-rose-600 font-semibold">AI summary failed: ' + escapeHtml(err.message) + '</div>';
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

/* Markdown Renderer */
function renderMarkdown(md) {
  if (!md) return '';
  if (typeof marked !== 'undefined' && marked.parse) {
    try {
      return marked.parse(md);
    } catch (e) {}
  }
  return escapeHtml(md)
    .replace(/^### (.*$)/gim, '<h3 class="font-bold text-sm text-slate-800 mt-2 mb-1">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="font-bold text-base text-slate-900 mt-3 mb-1">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="font-black text-lg text-slate-900 mt-3 mb-1">$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong class="font-bold text-slate-900">$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em class="italic">$1</em>')
    .replace(/^- (.*$)/gim, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n/gim, '<br>');
}

/* Description Editor Tab Switcher */
function switchDescTab(tab) {
  const isWrite = tab === 'write';
  const writeBtn = document.getElementById('descTabWrite');
  const prevBtn = document.getElementById('descTabPreview');
  if (writeBtn && prevBtn) {
    writeBtn.className = isWrite ? 'px-2 py-0.5 rounded font-bold bg-slate-200 text-slate-700' : 'px-2 py-0.5 rounded text-slate-500 hover:text-slate-700';
    prevBtn.className = !isWrite ? 'px-2 py-0.5 rounded font-bold bg-slate-200 text-slate-700' : 'px-2 py-0.5 rounded text-slate-500 hover:text-slate-700';
  }
  const textarea = document.getElementById('modalDesc');
  const preview = document.getElementById('modalDescPreview');
  if (textarea && preview) {
    if (isWrite) {
      textarea.classList.remove('hidden');
      preview.classList.add('hidden');
    } else {
      textarea.classList.add('hidden');
      preview.classList.remove('hidden');
      preview.innerHTML = renderMarkdown(textarea.value) || '<div class="text-slate-400 italic">No description provided yet.</div>';
    }
  }
}

/* Modal utils */
function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }
function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[m]);
}

// Initialize on DOM load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
