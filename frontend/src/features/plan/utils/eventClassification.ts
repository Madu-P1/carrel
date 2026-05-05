/**
 * Front-end mirror of `services/planning/deadlines.STUDY_ALLOCATION_KEYWORDS`.
 *
 * Both sides MUST agree on the regex — if they drift, the dashboard's
 * insertion engine and the calendar grid disagree about which events
 * are user-allocated study time, and the user sees an icon on a block
 * the engine doesn't credit (or vice versa). Tests in
 * `tests/test_planning_insertion.py::test_study_keyword_event_counts_as_allocated_prep`
 * pin the backend; this regex must stay synchronized.
 *
 * Keep it case-insensitive + word-bounded. `\b` matches transitions
 * between word + non-word chars, so:
 *   - "Study Bio" → matches
 *   - "Revise calculus" → matches
 *   - "Gym workout" → no match
 *   - "Studying log" → matches (separate keyword)
 *   - "Casestudy" → no match (no word boundary before "study")
 */
const STUDY_ALLOCATION_RE = /\b(study|studying|revision|revise)\b/i;

export function isUserStudyBlock(summary: string | null | undefined): boolean {
  if (!summary) return false;
  return STUDY_ALLOCATION_RE.test(summary);
}
