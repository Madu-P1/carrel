const ASK_QUESTION_TARGET = "[data-focus-target='ask-question']";

export function focusAskInput(): boolean {
  const field = document.querySelector<HTMLInputElement>(ASK_QUESTION_TARGET);
  if (!field) return false;
  field.focus();
  return document.activeElement === field;
}
