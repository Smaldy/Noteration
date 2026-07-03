import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Loader2,
  MinusCircle,
} from "lucide-react";

import type { TopicPriority } from "@/types/structure";
import type { TopicStatus } from "@/types/study";

interface TopicStatusIconProps {
  status: TopicStatus;
  priority: TopicPriority;
}

/** Sidebar status glyph: ✓ ready · ⟳ processing · … queued · ! error · skip. */
export function TopicStatusIcon({ status, priority }: TopicStatusIconProps) {
  if (priority === "skip") {
    return <MinusCircle className="size-4 shrink-0 text-muted-foreground/50" />;
  }
  switch (status) {
    case "ready":
      return <CheckCircle2 className="size-4 shrink-0 text-success" />;
    case "processing":
      return <Loader2 className="size-4 shrink-0 animate-spin text-info" />;
    case "error":
      return <AlertCircle className="size-4 shrink-0 text-destructive" />;
    case "queued":
    default:
      return <Circle className="size-4 shrink-0 text-muted-foreground" />;
  }
}
