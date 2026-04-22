import { state } from "../state.js";

export function renderStudyCard() {
  const current = state.dueCards[state.currentCardIndex];
  const label = document.getElementById("studyProgressLabel");
  const fill = document.getElementById("studyProgressFill");
  const front = document.getElementById("cardFront");
  const back = document.getElementById("cardBack");
  const showAnswerBtn = document.getElementById("showAnswerBtn");
  const ratingButtons = document.querySelectorAll(".rating-button");
  const progressCount = current ? state.currentCardIndex + 1 : state.dueCards.length;

  label.textContent = `${progressCount} / ${state.dueCards.length}`;
  fill.style.width = state.dueCards.length ? `${(state.currentCardIndex / state.dueCards.length) * 100}%` : "0%";

  if (!current) {
    front.textContent = "No cards due";
    back.textContent = "Your review queue is clear right now. Upload another document to generate more cards.";
    back.classList.remove("hidden");
    showAnswerBtn.classList.add("hidden");
    ratingButtons.forEach((button) => button.classList.add("hidden"));
    return;
  }

  document.getElementById("socraticTopic").textContent = `Topic: ${current.concept}`;
  front.textContent = current.front;
  back.textContent = current.back;
  back.classList.toggle("hidden", !state.showAnswer);
  showAnswerBtn.classList.toggle("hidden", state.showAnswer);
  ratingButtons.forEach((button) => button.classList.toggle("hidden", !state.showAnswer));
}
