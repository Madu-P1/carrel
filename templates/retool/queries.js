export const getQuizQuestions = `
Query database: Quiz Bank
Filter: Status = "Ready for review"
Sort: Created Date descending
`;

export const getTodaysSRSCards = `
Query database: SRS Cards
Filter: Due Date <= today()
Sort: Due Date ascending
`;

export const getSRSStats = `
const cards = getTodaysSRSCards.data || [];
return {
  totalDue: cards.length,
  mastered: cards.filter(c => Number(c['Ease Factor']) > 3.0).length,
  retention: cards.length ? ((cards.filter(c => c['Correct']).length / cards.length) * 100).toFixed(1) : '0.0'
};
`;

export const updateSRSCard = `
const card = getTodaysSRSCards.data[studyCard.currentCardIndex];
const rating = 3;
const ease = Number(card['Ease Factor'] || 2.5);
const interval = Number(card['Interval (days)'] || 1);

let newEase = ease + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02));
newEase = Math.max(1.3, newEase);

let newInterval;
if (rating < 3) newInterval = 1;
else if (interval === 1) newInterval = 3;
else newInterval = Math.round(interval * newEase);

const nextDueDate = new Date();
nextDueDate.setDate(nextDueDate.getDate() + newInterval);

updateSRSCard.trigger({
  additionalScope: {
    card_id: card.id,
    newEase: newEase.toFixed(2),
    newInterval,
    nextDueDate: nextDueDate.toISOString().split('T')[0],
    correct: rating >= 3
  }
});
`;

export const uploadToMake = `
const file = documentUploader.value[0];
const formData = new FormData();
formData.append('file', file);
formData.append('fileName', file.name);

fetch('YOUR_MAKE_WEBHOOK_URL', {
  method: 'POST',
  body: formData
});
`;
