const profile = document.querySelector('#profile-dialog');
document.querySelectorAll('[data-profile-open]').forEach(button => {
  button.addEventListener('click', () => profile.showModal());
});
document.querySelectorAll('[data-dialog-close]').forEach(button => {
  button.addEventListener('click', () => button.closest('dialog').close());
});
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
});
const picker = document.querySelector('#group-dialog');
let pickerRequest = 0;
document.querySelectorAll('[data-group-open]').forEach(link => {
  link.addEventListener('click', async event => {
    event.preventDefault();
    const request = ++pickerRequest;
    const activity = link.dataset.groupOpen === 'activity';
    const list = document.querySelector('#group-picker-list');
    document.querySelector('#group-picker-hint').textContent = activity ? "Whose shared tab would you like to catch up on?" : 'Where does this bill belong?';
    list.textContent = 'Loading your groups...';
    picker.showModal();
    try {
      const response = await fetch('/groups', {headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error('Unable to load groups.');
      const groups = await response.json();
      if (request !== pickerRequest) return;
      list.replaceChildren();
      if (!groups.length) list.textContent = 'Create your first group to start a shared tab.';
      for (const group of groups) {
        const item = document.createElement('a');
        item.className = 'sheet-option';
        item.href = `/groups/${group.id}${activity ? '/activity' : '#add-expense'}`;
        const avatar = document.createElement('span');
        avatar.className = 'avatar'; avatar.textContent = group.name.slice(0, 1).toUpperCase();
        const name = document.createElement('strong'); name.textContent = group.name;
        item.append(avatar, name); list.append(item);
      }
    } catch (_) {
      if (request !== pickerRequest) return;
      list.textContent = 'Your groups could not be loaded. ';
      const fallback = document.createElement('a'); fallback.href = '/groups'; fallback.textContent = 'Open your groups';
      list.append(fallback);
    }
  });
});
