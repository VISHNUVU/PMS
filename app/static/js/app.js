// ── Modal helpers ─────────────────────────────────────────────
function openModal(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.classList.remove('hidden');
  document.getElementById('modal-overlay').classList.remove('hidden');
  const first = m.querySelector('input:not([disabled]),textarea,select');
  if (first) setTimeout(() => first.focus(), 50);
}

function closeAllModals() {
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  const ov = document.getElementById('modal-overlay');
  if (ov) ov.classList.add('hidden');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeAllModals(); closeAllTaskEdits(); }
});

// ── Task inline edit ──────────────────────────────────────────
function openTaskEdit(id) {
  closeAllTaskEdits();
  const el = document.getElementById('task-edit-' + id);
  if (el) el.classList.remove('hidden');
}

function closeTaskEdit(id) {
  const el = document.getElementById('task-edit-' + id);
  if (el) el.classList.add('hidden');
}

function closeAllTaskEdits() {
  document.querySelectorAll('.task-inline-modal').forEach(m => m.classList.add('hidden'));
}

// Close task edits when clicking outside
document.addEventListener('click', e => {
  if (!e.target.closest('.task-card')) closeAllTaskEdits();
});

// ── Drag & Drop Kanban ────────────────────────────────────────
let draggedTaskId = null;

function dragStart(event, taskId) {
  draggedTaskId = taskId;
  event.dataTransfer.effectAllowed = 'move';
  setTimeout(() => {
    const card = document.querySelector(`[data-task-id="${taskId}"]`);
    if (card) card.classList.add('dragging');
  }, 0);
}

document.addEventListener('dragend', () => {
  document.querySelectorAll('.task-card').forEach(c => c.classList.remove('dragging'));
  document.querySelectorAll('.kanban-col').forEach(c => c.classList.remove('drag-over'));
});

async function dropTask(event, newStatus) {
  event.preventDefault();
  const col = event.currentTarget;
  col.classList.remove('drag-over');

  if (!draggedTaskId) return;

  try {
    const res = await fetch(`/tasks/${draggedTaskId}/update-status-ajax`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    if (res.ok) {
      showToast('Task moved to ' + newStatus.replace('_', ' '), 'success');
      setTimeout(() => window.location.reload(), 400);
    } else {
      showToast('Failed to update task', 'error');
    }
  } catch {
    showToast('Network error', 'error');
  }
  draggedTaskId = null;
}

// ── Toast notifications ───────────────────────────────────────
function showToast(msg, type = '') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${msg}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">×</button>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'slideOut .25s ease forwards';
    setTimeout(() => toast.remove(), 260);
  }, 3500);
}

// ── Dropdown ──────────────────────────────────────────────────
function toggleDropdown(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.dropdown')) {
    document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
  }
});

// ── Admin reset password modal ────────────────────────────────
function openResetModal(userId, userName) {
  const nameEl = document.getElementById('reset-user-name');
  const form   = document.getElementById('reset-pw-form');
  if (nameEl) nameEl.textContent = userName;
  if (form)   form.action = `/admin/users/${userId}/reset-password`;
  openModal('modal-reset-pw');
}

// ── Dark Mode ─────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('ebs-theme', theme);
}

function toggleDarkMode() {
  const current = document.documentElement.getAttribute('data-theme');
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// Apply saved theme immediately (before DOMContentLoaded to avoid flash)
(function() {
  const saved = localStorage.getItem('ebs-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
})();

// ── Auto-dismiss flash alerts + toast from URL ────────────────
document.addEventListener('DOMContentLoaded', () => {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(a => {
    setTimeout(() => {
      a.style.opacity = '0';
      a.style.transition = 'opacity .4s';
      setTimeout(() => a.remove(), 400);
    }, 4000);
  });

  // Show query-param based toasts
  const params = new URLSearchParams(window.location.search);
  const success = params.get('success');
  const error   = params.get('error');
  if (success) showToast(decodeURIComponent(success.replace(/\+/g,' ')), 'success');
  if (error)   showToast(decodeURIComponent(error.replace(/\+/g,' ')), 'error');

  // File upload label sync
  document.querySelectorAll('.upload-label input[type=file]').forEach(input => {
    input.addEventListener('change', function() {
      const label = this.closest('.upload-label')?.querySelector('.upload-filename');
      if (label) label.textContent = this.files[0]?.name || '';
    });
  });
});
