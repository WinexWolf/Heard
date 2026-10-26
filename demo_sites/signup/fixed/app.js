const terms = document.getElementById('terms');
const toggle = () => { terms.classList.toggle('on'); terms.setAttribute('aria-checked', terms.classList.contains('on') ? 'true' : 'false'); };
terms.addEventListener('click', toggle);
terms.addEventListener('keydown', e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(); } });
document.getElementById('signup').addEventListener('submit', e => {
  e.preventDefault();
  const email = document.getElementById('email').value;
  document.getElementById('email-error').textContent = /\S+@\S+\.\S+/.test(email) ? '' : 'Enter a valid email address.';
});
