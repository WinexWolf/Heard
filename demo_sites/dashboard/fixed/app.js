const tabs = [...document.querySelectorAll('.tab')];
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => { x.classList.remove('active'); x.setAttribute('aria-selected', 'false'); });
  t.classList.add('active'); t.setAttribute('aria-selected', 'true');
  document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== t.dataset.panel);
}));
tabs.forEach(t => t.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); t.click(); } }));
const modal = document.getElementById('modal');
const opener = document.getElementById('open-modal');
opener.addEventListener('click', () => { modal.hidden = false; document.getElementById('close-modal').focus(); });
modal.addEventListener('keydown', e => { if (e.key === 'Escape') { modal.hidden = true; opener.focus(); } });
document.getElementById('close-modal').addEventListener('click', () => { modal.hidden = true; opener.focus(); });
