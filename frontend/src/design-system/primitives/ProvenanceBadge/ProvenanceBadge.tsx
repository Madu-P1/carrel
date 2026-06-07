import { Badge } from "../Badge/Badge";

type ProvenanceTone = "neutral" | "success" | "warning" | "danger";
type ProvenanceLocation = "local" | "cloud" | "none";

interface ProviderDescriptor {
  label: string;
  tone: ProvenanceTone;
  // Local vs cloud is a distinct axis from the provider name and must never be
  // flattened away: it is the load-bearing claim for regulated counsel.
  location: ProvenanceLocation;
}

const PROVIDER_REGISTRY: Record<string, ProviderDescriptor> = {
  claude: { label: "Claude", tone: "success", location: "cloud" },
  afm: { label: "Apple Intelligence", tone: "neutral", location: "local" },
  ollama: { label: "Ollama", tone: "neutral", location: "local" },
  deterministic: { label: "Deterministic", tone: "neutral", location: "local" },
  null: { label: "Unavailable", tone: "danger", location: "none" },
};

const UNKNOWN_DESCRIPTOR: ProviderDescriptor = {
  label: "Unavailable",
  tone: "danger",
  location: "none",
};

const LOCATION_LABEL: Record<ProvenanceLocation, string> = {
  local: "On device",
  cloud: "Cloud",
  none: ""
};

export interface ProvenanceBadgeProps {
  provider: string;
  className?: string;
}

export function ProvenanceBadge({ provider, className }: ProvenanceBadgeProps) {
  const key = (provider ?? "").trim().toLowerCase();
  const descriptor = PROVIDER_REGISTRY[key] ?? UNKNOWN_DESCRIPTOR;
  const location = LOCATION_LABEL[descriptor.location];
  return (
    <Badge tone={descriptor.tone} className={className}>
      <span aria-hidden="true" style={{ marginRight: "6px", opacity: 0.7 }}>
        ◆
      </span>
      {descriptor.label}
      {location ? (
        <span style={{ marginLeft: "6px", opacity: 0.7 }}>· {location}</span>
      ) : null}
    </Badge>
  );
}
