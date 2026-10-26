const tabs = [...document.querySelectorAll('.tab')];
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== t.dataset.panel);
}));
tabs.forEach(t => t.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); t.click(); } }));
const modal = document.getElementById('modal');
document.getElementById('open-modal').addEventListener('click', () => { modal.hidden = false; });
document.getElementById('close-modal').addEventListener('click', () => { modal.hidden = true; });
