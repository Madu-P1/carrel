import styles from "./Icon.module.css";
import { icons, type IconName } from "./icons";

export interface IconProps {
  name: IconName;
  size?: number;
  title?: string;
}

export function Icon({ name, size = 16, title }: IconProps) {
  return (
    <svg
      aria-hidden={title ? undefined : true}
      className={styles.icon}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.5"
      viewBox="0 0 16 16"
      width={size}
    >
      {title ? <title>{title}</title> : null}
      <path d={icons[name]} />
    </svg>
  );
}
