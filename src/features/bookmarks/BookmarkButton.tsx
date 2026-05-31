import { Bookmark } from "lucide-react";

import { cn } from "@/lib/utils";

/** A star/bookmark toggle. Filled + accent-colored when active. */
export function BookmarkButton({
  bookmarked,
  onToggle,
  label,
  className,
  size = "md",
}: {
  bookmarked: boolean;
  onToggle: (next: boolean) => void;
  /** Accessible name of the thing being bookmarked, e.g. "Physics". */
  label: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const icon = size === "sm" ? "size-3.5" : "size-4";
  return (
    <button
      type="button"
      title={bookmarked ? "Remove bookmark" : "Bookmark"}
      aria-label={`${bookmarked ? "Remove bookmark from" : "Bookmark"} ${label}`}
      aria-pressed={bookmarked}
      onClick={(e) => {
        e.stopPropagation();
        onToggle(!bookmarked);
      }}
      className={cn(
        "rounded-md p-1 transition-all duration-150 active:scale-90",
        bookmarked
          ? "text-primary"
          : "text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      <Bookmark className={cn(icon, bookmarked && "fill-current")} />
    </button>
  );
}
