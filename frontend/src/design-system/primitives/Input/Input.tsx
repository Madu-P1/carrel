import type { ComponentChildren, JSX } from "preact";
import { useId } from "preact/hooks";

import styles from "./Input.module.css";

export interface InputProps
  extends Omit<JSX.InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: string;
  helpText?: string;
  error?: string;
  leadingIcon?: ComponentChildren;
}

export function Input({
  label,
  helpText,
  error,
  leadingIcon,
  id,
  className,
  ...rest
}: InputProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const describedBy = error ? `${fieldId}-error` : helpText ? `${fieldId}-help` : undefined;

  return (
    <label className={styles.field} htmlFor={fieldId}>
      {label ? <span className={styles.label}>{label}</span> : null}
      <span
        className={[
          styles.control,
          error ? styles.invalid : "",
          className ?? ""
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {leadingIcon ? <span className={styles.leading}>{leadingIcon}</span> : null}
        <input
          aria-describedby={describedBy}
          aria-invalid={error ? "true" : undefined}
          className={styles.input}
          id={fieldId}
          {...rest}
        />
      </span>
      {error ? (
        <span className={styles.error} id={`${fieldId}-error`}>
          {error}
        </span>
      ) : helpText ? (
        <span className={styles.help} id={`${fieldId}-help`}>
          {helpText}
        </span>
      ) : null}
    </label>
  );
}
