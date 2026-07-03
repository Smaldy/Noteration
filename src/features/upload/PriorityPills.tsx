import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { TopicPriority } from "@/types/structure";

const OPTIONS: { value: TopicPriority; key: string; active: string }[] = [
  { value: "exam_critical", key: "examCritical", active: "bg-primary text-primary-foreground" },
  { value: "medium", key: "medium", active: "bg-secondary text-secondary-foreground" },
  { value: "skip", key: "skip", active: "bg-muted text-muted-foreground line-through" },
];

interface PriorityPillsProps {
  value: TopicPriority;
  onChange: (priority: TopicPriority) => void;
}

export function PriorityPills({ value, onChange }: PriorityPillsProps) {
  const { t } = useTranslation();
  return (
    <div className="inline-flex rounded-lg border p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={cn(
            "rounded-md px-2 py-0.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === opt.value
              ? opt.active
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t(`upload.priority.${opt.key}`)}
        </button>
      ))}
    </div>
  );
}
