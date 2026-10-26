document.getElementById('cart-btn').addEventListener('click', () => document.getElementById('cart').scrollIntoView());
document.querySelectorAll('.edit-btn').forEach(b => b.addEventListener('click', () => { b.textContent = 'Done'; }));
document.querySelectorAll('.add').forEach(b => b.addEventListener('click', () => { b.textContent = 'Added'; }));
