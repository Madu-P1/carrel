import { Badge } from "../Badge/Badge";

type ProvenanceTone = "neutral" | "success" | "warning" | "danger";

interface ProviderDescriptor {
  label: string;
  tone: ProvenanceTone;
}

const PROVIDER_REGISTRY: Record<string, ProviderDescriptor> = {
  claude: { label: "Claude", tone: "success" },
  afm: { label: "Apple Intelligence", tone: "neutral" },
  ollama: { label: "Ollama", tone: "neutral" },
  null: { label: "Unavailable", tone: "danger" },
};

const UNKNOWN_DESCRIPTOR: ProviderDescriptor = {
  label: "Unavailable",
  tone: "danger",
};

export interface ProvenanceBadgeProps {
  provider: string;
  className?: string;
}

export function ProvenanceBadge({ provider, className }: ProvenanceBadgeProps) {
  const key = (provider ?? "").trim().toLowerCase();
  const descriptor = PROVIDER_REGISTRY[key] ?? UNKNOWN_DESCRIPTOR;
  return (
    <Badge tone={descriptor.tone} className={className}>
      <span aria-hidden="true" style={{ marginRight: "6px", opacity: 0.7 }}>
        ◆
      </span>
      {descriptor.label}
    </Badge>
  );
}
