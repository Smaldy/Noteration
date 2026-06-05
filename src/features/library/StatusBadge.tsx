import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/types/library";

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
  const { t } = useTranslation();
  return <Badge variant={VARIANTS[status]}>{t(`library.status.${status}`)}</Badge>;
}
