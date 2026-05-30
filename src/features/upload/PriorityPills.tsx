import { cn } from "@/lib/utils";
import type { TopicPriority } from "@/types/structure";

const OPTIONS: { value: TopicPriority; label: string; active: string }[] = [
  { value: "exam_critical", label: "Exam-critical", active: "bg-primary text-primary-foreground" },
  { value: "medium", label: "Medium", active: "bg-secondary text-secondary-foreground" },
  { value: "skip", label: "Skip", active: "bg-muted text-muted-foreground line-through" },
];

interface PriorityPillsProps {
  value: TopicPriority;
  onChange: (priority: TopicPriority) => void;
}

export function PriorityPills({ value, onChange }: PriorityPillsProps) {
  return (
    <div className="inline-flex rounded-md border p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={cn(
            "rounded px-2 py-0.5 text-xs font-medium transition-colors",
            value === opt.value
              ? opt.active
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
