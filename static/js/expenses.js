document.querySelectorAll('select[name="split_mode"]').forEach((mode) => {
  const form = mode.closest('form');
  const update = () => {
    const unequal = mode.value === 'unequal';
    form.querySelectorAll('input[name^="share_"]').forEach((input) => {
      input.closest('p').hidden = !unequal;
      input.disabled = !unequal;
    });
    const participants = form.querySelector('select[name="participants"]');
    if (participants) {
      participants.closest('p').hidden = unequal;
      participants.disabled = unequal;
    }
  };
  mode.addEventListener('change', update);
  update();
});
