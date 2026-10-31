"use strict";

document.querySelectorAll('[data-chart]').forEach(chart => {
  const rows = [...chart.querySelectorAll('[data-value]')];
  const values = rows.map(row => {
    const [whole, fraction = ''] = row.dataset.value.split('.');
    return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  });
  const scale = chart.dataset.chart === 'category'
    ? values.reduce((sum, value) => sum + value, 0n)
    : values.reduce((max, value) => value > max ? value : max, 0n);
  rows.forEach((row, index) => {
    row.style.setProperty('--chart-size', `${scale ? values[index] * 100n / scale : 0n}%`);
    row.title = `${row.textContent.trim()}${chart.dataset.chart === 'months' ? ` · INR ${row.dataset.value}` : ''}`;
  });
});

document.querySelectorAll("[data-copy], [data-share]").forEach((button) => {
  if (button.dataset.share && navigator.share) button.hidden = false;
  button.addEventListener("click", async () => {
    const field = document.getElementById(button.dataset.copy || button.dataset.share);
    const status = button.closest("section").querySelector(".share-status");
    try {
      if (button.dataset.share) {
        await navigator.share({text: field.value});
        status.textContent = "Share sheet closed.";
      } else {
        await navigator.clipboard.writeText(field.value);
        status.textContent = "Reminder copied.";
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      field.focus();
      field.select();
      status.textContent = "Select and copy the reminder text to share it.";
    }
  });
});
