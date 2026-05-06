import type { JSX } from "preact";

import { Button, Icon, Input } from "@/design-system";

import styles from "../AskView.module.css";

interface QuestionInputProps {
  disabled?: boolean;
  error?: string | null;
  onSubmit: () => void;
  onValueChange: (value: string) => void;
  value: string;
}

export function QuestionInput({
  disabled = false,
  error = null,
  onSubmit,
  onValueChange,
  value
}: QuestionInputProps) {
  const handleSubmit = (event: JSX.TargetedEvent<HTMLFormElement, Event>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form className={styles.questionRow} onSubmit={handleSubmit}>
      {/*
       * Serif voice on the question itself — per the brief §3.3, the user's
       * question is one of the "big moments." We pass a className that the
       * Input primitive forwards to its underlying <input>; if the primitive
       * doesn't forward it, the class still reaches the outer wrapper and
       * the `.questionInputField input` rule below catches the real field.
       *
       * The Input primitive's `label` prop renders the mono uppercase
       * "QUESTION" eyebrow above the field — that's the canonical
       * design-system pattern for form fields. Previously this component
       * also rendered an h3 "Your question" above the eyebrow; removed
       * because it was a third label for the same field (page heading
       * "Ask from your sources." already establishes the section, the
       * Input's "QUESTION" labels the field, and an h3 between them
       * just restated what was above and below it).
       */}
      <Input
        // The Ask page's primary affordance is "type your question." Auto-
        // focusing the field is an expected UX pattern — same as Spotlight
        // or any command palette — and there's only one input on the page,
        // so there's no contention for keyboard focus.
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus
        className={styles.questionInputField}
        data-focus-target="ask-question"
        error={error ?? undefined}
        helpText={
          error
            ? undefined
            : "Answers cite only the chunks the retriever found in your library."
        }
        label="Question"
        onInput={(event) => {
          onValueChange((event.currentTarget as HTMLInputElement).value);
        }}
        placeholder="What do you want to understand?"
        value={value}
      />
      <Button
        disabled={disabled || !value.trim()}
        isLoading={disabled}
        keyHint="↵"
        leadingIcon={<Icon name="sparkle" />}
        type="submit"
      >
        Ask
      </Button>
    </form>
  );
}
