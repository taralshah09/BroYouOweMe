(() => {
  const initial = JSON.parse(document.getElementById('receipt-initial').textContent);
  const members = JSON.parse(document.getElementById('receipt-members').textContent);
  const byId = id => document.getElementById(id);
  const upload = byId('receipt-upload'), form = byId('receipt-review');
  const group = Number(upload.dataset.group);
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const error = byId('receipt-error'), status = byId('receipt-status');
  function element(tag, attrs = {}, text = '') {
    const node = document.createElement(tag);
    Object.assign(node, attrs); node.textContent = text; return node;
  }
  for (const member of members) {
    const label = element('label');
    label.append(element('input', {type: 'checkbox', value: String(member.user_id), checked: !initial.participants || initial.participants.includes(member.user_id)}), document.createTextNode(` ${member.user__username} `));
    byId('receipt-participants').append(label);
  }
  byId('description').value = initial.description;
  byId('expense-date').value = initial.expense_date;
  byId('receipt-total').value = initial.amount || '';
  byId('receipt-mode').value = initial.split_mode;
  function line(row = {}) {
    const box = element('fieldset'); box.append(element('legend', {}, 'Receipt line'));
    const kind = element('select', {className: 'line-kind', ariaLabel: 'Line kind'});
    for (const value of ['item', 'tax', 'service', 'tip', 'discount']) kind.append(element('option', {value}, value));
    kind.value = row.kind || 'item';
    const name = element('input', {className: 'line-name', placeholder: 'Name', ariaLabel: 'Line name', maxLength: 120, required: true, value: row.name || ''});
    const amount = element('input', {className: 'line-amount', placeholder: 'INR', ariaLabel: 'Line amount in INR', inputMode: 'decimal', pattern: '-?[0-9]+([.][0-9]{1,2})?', required: true, value: row.amount || ''});
    const payees = element('select', {className: 'line-payees', multiple: true, ariaLabel: 'Item payees (blank means all participants)'});
    for (const member of members) payees.append(element('option', {value: String(member.user_id), selected: (row.payees || []).includes(member.user_id)}, member.user__username));
    const toggle = () => { payees.disabled = kind.value !== 'item'; if (payees.disabled) for (const option of payees.options) option.selected = false; };
    kind.addEventListener('change', toggle); toggle();
    const remove = element('button', {type: 'button', className: 'secondary'}, 'Remove line');
    remove.addEventListener('click', () => {box.remove(); sum();});
    box.append(kind, name, amount, payees, remove); byId('receipt-lines').append(box);
    box.addEventListener('input', sum); sum();
  }
  function sum() {
    let total = 0n;
    for (const input of form.querySelectorAll('.line-amount')) {
      if (!/^-?\d+(\.\d{1,2})?$/.test(input.value)) { byId('receipt-sum').textContent = 'Complete every line amount.'; return; }
      const [whole, fraction = ''] = input.value.replace('-', '').split('.');
      total += (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))) * (input.value.startsWith('-') ? -1n : 1n);
    }
    const magnitude = total < 0n ? -total : total;
    byId('receipt-sum').textContent = `Lines total: INR ${total < 0n ? '-' : ''}${magnitude / 100n}.${String(magnitude % 100n).padStart(2, '0')}. Must match the receipt total.`;
  }
  for (const row of initial.items) line(row);
  byId('receipt-add').addEventListener('click', () => line());
  async function responseData(response) {
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : JSON.stringify(data.errors || data));
    return data;
  }
  upload.addEventListener('submit', async event => {
    event.preventDefault(); const button = upload.querySelector('button'); button.disabled = true;
    status.textContent = 'Reading receipt…';
    try {
      const image = byId('image').files[0];
      if (!image || image.size > 8 * 1024 * 1024) throw new Error('Choose an image up to 8 MiB.');
      const body = new FormData(); body.append('image', image);
      const draft = await responseData(await fetch(`/groups/${group}/receipts/parse`, {method: 'POST', headers: {'X-CSRFToken': csrf}, body}));
      byId('receipt-lines').replaceChildren(); for (const row of draft.items) line(row);
      byId('receipt-total').value = draft.amount; byId('receipt-text').textContent = draft.text;
      byId('receipt-extraction').open = !draft.items.some(row => row.kind === 'item');
      status.textContent = draft.warnings.join(' '); sum();
    } catch (issue) { status.textContent = issue.message; } finally { button.disabled = false; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.textContent = ''; byId('receipt-approve').disabled = true;
    const data = {source: 'ocr', paid_by: initial.paid_by_id || initial.paid_by, description: byId('description').value,
      amount: byId('receipt-total').value, expense_date: byId('expense-date').value,
      split_mode: byId('receipt-mode').value,
      participants: [...byId('receipt-participants').querySelectorAll('input:checked')].map(node => Number(node.value)),
      items: [...byId('receipt-lines').children].map(box => ({kind: box.querySelector('.line-kind').value, name: box.querySelector('.line-name').value,
        amount: box.querySelector('.line-amount').value, payees: [...box.querySelector('.line-payees').selectedOptions].map(node => Number(node.value))}))};
    if (!initial.id) data.group_id = group;
    try {
      const saved = await responseData(await fetch(initial.id ? `/expenses/${initial.id}` : '/expenses', {method: initial.id ? 'PATCH' : 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(data)}));
      window.location.assign(`/expenses/${saved.id}`);
    } catch (issue) { error.textContent = issue.message; byId('receipt-approve').disabled = false; }
  });
})();
