import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { type ComponentType, Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

// Always-mounted (visible on every route), so they stay in the main bundle.
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppSidebar } from "@/components/AppSidebar";
import { ArcadeRoot } from "@/features/arcade/ArcadeRoot";
import { AssistantLauncher } from "@/features/assistant/AssistantLauncher";
import { CreditsOverlay } from "@/features/credits/CreditsOverlay";
import { PomodoroWidget } from "@/features/pomodoro/PomodoroWidget";
import { ProviderBadge } from "@/features/queue/ProviderBadge";
import { TodoWidget } from "@/features/todo/TodoWidget";
import { cn } from "@/lib/utils";
import { useAssistantOffset, useAssistantStore } from "@/stores/assistant";
import { useSettingsStore } from "@/stores/settings";

// Route pages are code-split: each loads on demand so heavy libraries
// (FullCalendar, TipTap, KaTeX, react-markdown) stay out of the initial bundle
// and only download with the page that needs them. `named` adapts our named
// exports to the default export React.lazy expects.
function named<K extends string>(
  loader: () => Promise<Record<K, ComponentType>>,
  name: K,
) {
  return lazy(() => loader().then((m) => ({ default: m[name] })));
}

const LibraryPage = named(() => import("@/features/library/LibraryPage"), "LibraryPage");
const FolderPage = named(() => import("@/features/library/FolderPage"), "FolderPage");
const ExamPrepPage = named(() => import("@/features/exam/ExamPrepPage"), "ExamPrepPage");
const ExamPracticePage = named(() => import("@/features/exam/ExamPracticePage"), "ExamPracticePage");
const CalendarPage = named(() => import("@/features/calendar/CalendarPage"), "CalendarPage");
const QueuePage = named(() => import("@/features/queue/QueuePage"), "QueuePage");
const SettingsPage = named(() => import("@/features/settings/SettingsPage"), "SettingsPage");
const StructureReviewPage = named(() => import("@/features/upload/StructureReviewPage"), "StructureReviewPage");
const StudyPage = named(() => import("@/features/study/StudyPage"), "StudyPage");
const DuplicatorPage = named(() => import("@/features/duplicator/DuplicatorPage"), "DuplicatorPage");
// Not a route, but lazy for the same reason: it pulls in MarkdownView (KaTeX),
// which must not join the initial bundle. Loaded on first open, then kept.
const AssistantSidebar = named(() => import("@/features/assistant/AssistantSidebar"), "AssistantSidebar");

// App shell + routing. Library is the home screen (Phase 9b); structure review
// is the upload gate (Phase 9c); study view is Phase 9d; queue is Phase 9e;
// settings is Phase 9f; calendar is Phase 9g.
export default function App() {
  // Load settings once at boot so the persisted theme/font apply app-wide.
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);
  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  const location = useLocation();

  return (
    // Honor the OS "reduce motion" preference for every Framer Motion animation
    // (transforms collapse to instant; opacity fades are kept, per Framer's rule).
    <AppErrorBoundary>
      <MotionConfig reducedMotion="user">
        <AppSidebar />
        {/* Inset matches AppSidebar's fixed width; the sidebar sits outside the
            AnimatePresence so it doesn't re-animate on every navigation. */}
        <div className="pl-[4.5rem] lg:pl-60">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              <Suspense fallback={<RouteFallback />}>
                <Routes location={location}>
                  <Route path="/" element={<LibraryPage />} />
                  <Route path="/folders/:id" element={<FolderPage />} />
                  <Route path="/exam" element={<ExamPrepPage />} />
                  <Route path="/duplicator" element={<DuplicatorPage />} />
                  <Route path="/exam/practice/:scope/:id" element={<ExamPracticePage />} />
                  <Route path="/calendar" element={<CalendarPage />} />
                  <Route path="/queue" element={<QueuePage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/documents/:id/review" element={<StructureReviewPage />} />
                  <Route path="/documents/:id/study" element={<StudyPage />} />
                  <Route path="/documents/:id/study/:topicId" element={<StudyPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </div>
        {/* Persistent across routes — always-visible status + the running timer. */}
        <ProviderBadge />
        <FloatingWidgets />
        {/* Hidden easter egg: tap the Library title 4× quickly to summon the credits. */}
        <CreditsOverlay />
        {/* Study-gated arcade minigame — additive overlay; never touches the app. */}
        <ArcadeRoot />
        {/* The docked AI sidebar (the app's only chat surface). */}
        <AssistantRoot />
      </MotionConfig>
    </AppErrorBoundary>
  );
}

/** The bottom-right floating widgets (assistant + to-do list + Pomodoro), side
 *  by side in one fixed container. Lifted above the Settings page's sticky save
 *  bar, and shifted left of the AI sidebar while it is docked open. */
function FloatingWidgets() {
  const onSettings = useLocation().pathname === "/settings";
  const assistantOffset = useAssistantOffset();
  return (
    <div
      style={{ right: assistantOffset + 16 }}
      className={cn(
        "fixed z-40 flex items-end gap-2 transition-[right] duration-200 print:hidden",
        onSettings ? "bottom-24" : "bottom-4",
      )}
    >
      <AssistantLauncher />
      <TodoWidget />
      <PomodoroWidget />
    </div>
  );
}

/** Mounts the lazy sidebar chunk on first open, then keeps it mounted so the
 *  open/close slide animates and the thread survives toggling. */
function AssistantRoot() {
  const open = useAssistantStore((s) => s.open);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (open) setLoaded(true);
  }, [open]);
  if (!loaded) return null;
  return (
    <Suspense fallback={null}>
      <AssistantSidebar />
    </Suspense>
  );
}

/** Minimal placeholder shown while a route's chunk loads (usually instant on
 *  localhost). Kept quiet so it doesn't flash against the page transition. */
function RouteFallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <span className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
    </div>
  );
}
