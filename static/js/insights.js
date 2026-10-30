"use strict";

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
