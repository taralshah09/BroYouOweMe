document.querySelectorAll('select[name="split_mode"]').forEach((mode) => {
  const form = mode.closest('form');
  const update = () => {
    const unequal = mode.value === 'unequal';
    form.querySelectorAll('input[name^="share_"]').forEach((input) => {
      input.closest('.field-row, p').hidden = !unequal;
      input.disabled = !unequal;
    });
    form.querySelectorAll('[name="participants"]').forEach((input) => {
      input.closest('.field-row, p').hidden = unequal;
      input.disabled = unequal;
    });
  };
  mode.addEventListener('change', update);
  update();
});

document.querySelectorAll('.expense-form').forEach((form) => {
  const amount = form.querySelector('[name="amount"]');
  const mode = form.querySelector('[name="split_mode"]');
  const people = [...form.querySelectorAll('input[name="participants"]')];
  if (!amount || !mode || !people.length) return;
  const summary = document.createElement('p');
  summary.className = 'split-summary';
  summary.setAttribute('role', 'status');
  summary.setAttribute('aria-live', 'polite');
  mode.closest('.field-row, p').after(summary);
  const parse = (value) => {
    if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
    const [whole, fraction = ''] = value.split('.');
    return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  };
  const money = (paise) => `₹${paise / 100n}.${String(paise % 100n).padStart(2, '0')}`;
  const shares = people.map((input) => {
    const output = document.createElement('span');
    output.className = 'participant-share money';
    input.closest('label').append(output);
    return output;
  });
  const update = () => {
    const total = parse(amount.value);
    const selected = people.some((person) => person.checked) ? people.filter((person) => person.checked) : people;
    shares.forEach((output) => { output.textContent = ''; });
    if (total === null || total === 0n) {
      summary.textContent = 'Enter the bill amount to see the split.';
      summary.classList.remove('negative');
      return;
    }
    if (mode.value === 'unequal') {
      const allocated = [...form.querySelectorAll('input[name^="share_"]')].reduce((sum, input) => sum + (parse(input.value) ?? 0n), 0n);
      const remaining = total - allocated;
      summary.textContent = remaining === 0n ? 'Every share adds up. Ready to save.' : remaining > 0n ? `${money(remaining)} still to allocate.` : `${money(-remaining)} over the bill total.`;
      summary.classList.toggle('negative', remaining !== 0n);
    } else {
      const count = BigInt(selected.length);
      selected.forEach((person, index) => {
        shares[people.indexOf(person)].textContent = money(total / count + (BigInt(index) < total % count ? 1n : 0n));
      });
      summary.textContent = `${selected.length} people · ${money(total)} split in full.`;
      summary.classList.remove('negative');
    }
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  update();
});
