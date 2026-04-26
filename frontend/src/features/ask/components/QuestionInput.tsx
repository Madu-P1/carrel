import type { JSX } from "preact";

import { Button, Icon, Input, Stack, Text } from "@/design-system";

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
    <Stack gap={2}>
      <Text variant="h3" weight="semibold">
        Your question
      </Text>
      <form className={styles.questionRow} onSubmit={handleSubmit}>
        {/*
         * Serif voice on the question itself — per the brief §3.3, the user's
         * question is one of the "big moments." We pass a className that the
         * Input primitive forwards to its underlying <input>; if the primitive
         * doesn't forward it, the class still reaches the outer wrapper and
         * the `.questionInputField input` rule below catches the real field.
         */}
        <Input
          autoFocus
          className={styles.questionInputField}
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
          placeholder="How do mitosis checkpoints respond to DNA damage?"
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
    </Stack>
  );
}
