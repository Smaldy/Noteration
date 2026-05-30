import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/types/library";

const LABELS: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Ready",
  error: "Error",
};

const VARIANTS: Record<
  DocumentStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  uploaded: "outline",
  processing: "secondary",
  ready: "default",
  error: "destructive",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return <Badge variant={VARIANTS[status]}>{LABELS[status]}</Badge>;
}
