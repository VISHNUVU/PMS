function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeAllModals() {
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  document.getElementById('modal-overlay').classList.add('hidden');
}

function openTaskModal(taskId) {
  document.querySelectorAll('.task-inline-modal').forEach(m => m.classList.add('hidden'));
  document.getElementById('task-modal-' + taskId).classList.remove('hidden');
}

function closeTaskModal(taskId) {
  document.getElementById('task-modal-' + taskId).classList.add('hidden');
}

function openResetModal(userId, userName) {
  document.getElementById('reset-user-name').textContent = userName;
  document.getElementById('reset-pw-form').action = '/admin/users/' + userId + '/reset-password';
  openModal('modal-reset-pw');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeAllModals();
});
