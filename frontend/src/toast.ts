/** One global error channel so every failed API write is visible, not only inline. */
export function toast(message: string) {
  window.dispatchEvent(new CustomEvent("studio-toast", { detail: message }));
}
