import type { JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Badge, Card, Icon, Stack, Text } from "@/design-system";
import { search, type SearchHit } from "@/services/api/endpoints";
import { friendlyError } from "@/services/api/errorMessages";

import styles from "./SearchView.module.css";

/**
 * Library-wide search.
 *
 * Wraps `/api/search`, which fuses BM25 keyword hits and dense-vector
 * hits via reciprocal rank fusion. The point of having both:
 *
 *   - keyword search nails proper nouns and exact phrases ("Black-Scholes")
 *   - vector search nails semantic intent ("how do options get priced")
 *
 * Together they catch the union. Results carry a `sources` array
 * indicating which retriever surfaced each hit; chunks that came from
 * BOTH retrievers get a stronger accent in the UI because they're
 * typically the most relevant.
 *
 * Voice rules (per the Carrel design package §"Voice Rules"):
 *   - Mono uppercase eyebrow + serif h1 sentence-case heading + sans subhead
 *   - Empty states ship a CTA, not just text
 *   - Errors name a concrete recovery action
 *
 * Keyboard:
 *   - Enter inside the input runs the search immediately (no debounce wait).
 *   - Click any result → navigate to `/reader/{doc_id}?chunk={chunk_id}`,
 *     which triggers the citation-flight pulseOnce on the target chunk
 *     via `useCitationFlight` already wired in the Reader.
 *
 * Debounce: 280ms after typing stops. Slow enough to avoid hammering the
 * embedder on every keystroke, fast enough to feel live. The user can
 * always press Enter to skip the debounce.
 */

const DEBOUNCE_MS = 280;
const MIN_QUERY_CHARS = 2;

type Phase = "idle" | "loading" | "ready" | "error";

interface SearchState {
  phase: Phase;
  hits: SearchHit[];
  /** Raw error from the search request — Error subclass when present,
   *  null otherwise. The renderer pipes it through friendlyError() so
   *  BackendOfflineError gets a different copy than ApiError. */
  error: unknown;
  /** The query string that produced `hits`. May lag the input value
   *  while a new debounced search is in flight. */
  resolvedQuery: string;
}

const INITIAL_STATE: SearchState = {
  phase: "idle",
  hits: [],
  error: null,
  resolvedQuery: "",
};

export function SearchView() {
  const [value, setValue] = useState("");
  const [state, setState] = useState<SearchState>(INITIAL_STATE);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // A monotonic request id so an out-of-order late response from a
  // previous query doesn't overwrite a newer one. Increment on every
  // dispatch; ignore the response if it isn't the latest.
  const reqIdRef = useRef(0);
  const debounceRef = useRef<number | null>(null);

  // Autofocus on mount. Cmd-F or hitting / on the dashboard could land
  // here later; for now the URL navigates here directly.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const runSearch = (rawQuery: string) => {
    const trimmed = rawQuery.trim();
    if (trimmed.length < MIN_QUERY_CHARS) {
      setState({ ...INITIAL_STATE });
      return;
    }
    const id = ++reqIdRef.current;
    setState((prev) => ({ ...prev, phase: "loading", error: null }));
    search
      .query({ q: trimmed, limit: 20 })
      .then((response) => {
        if (id !== reqIdRef.current) return; // a newer request has overtaken us
        setState({
          phase: "ready",
          hits: response.results,
          error: null,
          resolvedQuery: response.query,
        });
      })
      .catch((err) => {
        if (id !== reqIdRef.current) return;
        setState({
          phase: "error",
          hits: [],
          error: err,
          resolvedQuery: trimmed,
        });
      });
  };

  // Debounced auto-search as the user types. Cancel pending debounce on
  // every keystroke so only the LAST quiet 280ms triggers a request.
  useEffect(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    if (value.trim().length < MIN_QUERY_CHARS) {
      // Below the floor — clear the result set so stale hits don't linger
      // when the user backspaces past it.
      setState({ ...INITIAL_STATE });
      return;
    }
    debounceRef.current = window.setTimeout(() => {
      runSearch(value);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
    // runSearch is stable for our purposes — it only reads the request-id ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const onSubmit = (event: JSX.TargetedEvent<HTMLFormElement, Event>) => {
    event.preventDefault();
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    runSearch(value);
  };

  const handleResultClick = (hit: SearchHit) => {
    // Reader URL with a `chunk` query param triggers the deep-link
    // scroll + citation-flight pulseOnce in the Reader view.
    const path = `/reader/${encodeURIComponent(hit.doc_id)}?chunk=${encodeURIComponent(hit.chunk_id)}`;
    navigateTo(path);
  };

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>Library search</span>
        <h1 className={styles.heading}>Find the chunk.</h1>
        <Text tone="secondary">
          Hybrid keyword + semantic search across every source you've
          imported. Results land at the chunk; click any hit to open it
          in the Reader.
        </Text>
      </header>

      <form className={styles.searchRow} onSubmit={onSubmit} role="search">
        <div className={styles.inputWell}>
          <span className={styles.inputIcon} aria-hidden>
            <Icon name="search" size={16} />
          </span>
          <input
            ref={inputRef}
            type="search"
            value={value}
            onInput={(e) =>
              setValue((e.currentTarget as HTMLInputElement).value)
            }
            placeholder="Black-Scholes, dividend discount model, mitosis…"
            className={styles.input}
            autoComplete="off"
            spellcheck={true}
            aria-label="Search your library"
          />
          {state.phase === "loading" ? (
            <span className={styles.statusChip}>Searching…</span>
          ) : null}
        </div>
      </form>

      <ResultsBlock
        state={state}
        onResultClick={handleResultClick}
        onRetry={() => runSearch(value)}
      />
    </div>
  );
}

interface ResultsBlockProps {
  state: SearchState;
  onResultClick: (hit: SearchHit) => void;
  onRetry: () => void;
}

function ResultsBlock({ state, onResultClick, onRetry }: ResultsBlockProps) {
  if (state.phase === "idle") {
    return <SearchEmptyState />;
  }

  if (state.phase === "error") {
    const friendly = friendlyError(state.error, { surface: "Search" });
    return (
      <Card padding="lg">
        <Stack gap={3}>
          <span className={styles.stateEyebrow}>{friendly.title}</span>
          <Text as="h2" className={styles.stateHeading}>
            Couldn't run the search.
          </Text>
          <Text tone="secondary">{friendly.detail}</Text>
          {friendly.recovery ? (
            <Text tone="tertiary">{friendly.recovery}</Text>
          ) : null}
          <div>
            <button type="button" className={styles.retryButton} onClick={onRetry}>
              Run the search again
            </button>
          </div>
        </Stack>
      </Card>
    );
  }

  if (state.phase === "loading" && state.hits.length === 0) {
    // First-fetch loading: hold the layout with a single skeleton row so
    // the "no results" state below doesn't flash before the response lands.
    return <div className={styles.skeletonList} />;
  }

  if (state.hits.length === 0) {
    return (
      <Card padding="lg">
        <Stack gap={3}>
          <span className={styles.stateEyebrow}>No matches</span>
          <Text as="h2" className={styles.stateHeading}>
            Nothing in your library matches "{state.resolvedQuery}".
          </Text>
          <Text tone="secondary">
            Try a shorter phrase, a more general term, or check Library to
            confirm you've imported the right source.
          </Text>
        </Stack>
      </Card>
    );
  }

  return (
    <Stack gap={3} aria-label="Search results">
      <div className={styles.resultsCount}>
        {state.hits.length} result{state.hits.length === 1 ? "" : "s"} for
        <span className={styles.resultsQuery}> "{state.resolvedQuery}"</span>
      </div>
      <div className={styles.resultsList}>
        {state.hits.map((hit) => (
          <SearchResultRow
            key={hit.chunk_id}
            hit={hit}
            onClick={() => onResultClick(hit)}
          />
        ))}
      </div>
    </Stack>
  );
}

function SearchEmptyState() {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <span className={styles.stateEyebrow}>Ready</span>
        <Text as="h2" className={styles.stateHeading}>
          Type a phrase or concept.
        </Text>
        <Text tone="secondary">
          Search runs across both exact wording (BM25 keyword) and meaning
          (dense-vector similarity). Two characters minimum. Results land
          on the chunk in the Reader.
        </Text>
      </Stack>
    </Card>
  );
}

interface SearchResultRowProps {
  hit: SearchHit;
  onClick: () => void;
}

function SearchResultRow({ hit, onClick }: SearchResultRowProps) {
  const filename = hit.filename ?? "Unknown source";
  const subject = hit.subject_name ?? null;
  const page = hit.page_num ?? null;
  // A chunk is "doubly retrieved" when both FTS and vector surfaced it —
  // that's the strongest signal of relevance. Show a stronger accent.
  const isDoubleHit = hit.sources.includes("fts") && hit.sources.includes("vec");
  // Sources -> readable badge tone for the per-row chip.
  const sourceLabel = isDoubleHit
    ? "Keyword + semantic"
    : hit.sources.includes("fts")
      ? "Keyword"
      : "Semantic";

  return (
    <button
      type="button"
      className={[styles.resultRow, isDoubleHit ? styles.resultRowStrong : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={onClick}
    >
      <div className={styles.resultMeta}>
        <span className={styles.resultFilename}>{filename}</span>
        <span className={styles.resultMetaDot} aria-hidden>·</span>
        {subject ? (
          <>
            <span className={styles.resultSubject}>{subject}</span>
            <span className={styles.resultMetaDot} aria-hidden>·</span>
          </>
        ) : null}
        {page !== null ? (
          <span className={styles.resultPage}>p. {page}</span>
        ) : null}
      </div>
      <SnippetWithMarks raw={hit.snippet} />
      <div className={styles.resultFooter}>
        <Badge tone={isDoubleHit ? "info" : "neutral"}>{sourceLabel}</Badge>
        {hit.section ? (
          <span className={styles.resultSection}>{hit.section}</span>
        ) : null}
      </div>
    </button>
  );
}

/**
 * The FTS retriever wraps matching tokens in `<<` / `>>` per the SQL
 * `snippet()` call in `services/retrieval/fts.py`. Render those as
 * accent-highlighted spans without ever interpreting the snippet as
 * HTML — the snippet contains arbitrary user-source text which can
 * include real `<` / `>` from formulas, tags, etc. Plain text only,
 * marker-aware.
 */
function SnippetWithMarks({ raw }: { raw: string }) {
  const parts: JSX.Element[] = [];
  let cursor = 0;
  let key = 0;
  while (cursor < raw.length) {
    const start = raw.indexOf("<<", cursor);
    if (start === -1) {
      parts.push(<span key={`t${key++}`}>{raw.slice(cursor)}</span>);
      break;
    }
    if (start > cursor) {
      parts.push(<span key={`t${key++}`}>{raw.slice(cursor, start)}</span>);
    }
    const end = raw.indexOf(">>", start + 2);
    if (end === -1) {
      // Unterminated marker — render the rest as plain.
      parts.push(<span key={`t${key++}`}>{raw.slice(start)}</span>);
      break;
    }
    parts.push(
      <mark key={`m${key++}`} className={styles.snippetMark}>
        {raw.slice(start + 2, end)}
      </mark>
    );
    cursor = end + 2;
  }
  return <p className={styles.snippet}>{parts}</p>;
}
