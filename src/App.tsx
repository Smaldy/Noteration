import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { type ComponentType, Suspense, lazy, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

// Always-mounted (visible on every route), so they stay in the main bundle.
import { ArcadeRoot } from "@/features/arcade/ArcadeRoot";
import { CreditsOverlay } from "@/features/credits/CreditsOverlay";
import { PomodoroWidget } from "@/features/pomodoro/PomodoroWidget";
import { ProviderBadge } from "@/features/queue/ProviderBadge";
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
const ExamPrepPage = named(() => import("@/features/exam/ExamPrepPage"), "ExamPrepPage");
const ExamPracticePage = named(() => import("@/features/exam/ExamPracticePage"), "ExamPracticePage");
const BookmarksPage = named(() => import("@/features/bookmarks/BookmarksPage"), "BookmarksPage");
const CalendarPage = named(() => import("@/features/calendar/CalendarPage"), "CalendarPage");
const QueuePage = named(() => import("@/features/queue/QueuePage"), "QueuePage");
const SettingsPage = named(() => import("@/features/settings/SettingsPage"), "SettingsPage");
const StructureReviewPage = named(() => import("@/features/upload/StructureReviewPage"), "StructureReviewPage");
const StudyPage = named(() => import("@/features/study/StudyPage"), "StudyPage");
const DuplicatorPage = named(() => import("@/features/duplicator/DuplicatorPage"), "DuplicatorPage");

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
    <MotionConfig reducedMotion="user">
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
              <Route path="/exam" element={<ExamPrepPage />} />
              <Route path="/duplicator" element={<DuplicatorPage />} />
              <Route path="/exam/practice/:scope/:id" element={<ExamPracticePage />} />
              <Route path="/bookmarks" element={<BookmarksPage />} />
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
      {/* Persistent across routes — always-visible status + the running timer. */}
      <ProviderBadge />
      <PomodoroWidget />
      {/* Hidden easter egg: tap the Library title 4× quickly to summon the credits. */}
      <CreditsOverlay />
      {/* Study-gated arcade minigame — additive overlay; never touches the app. */}
      <ArcadeRoot />
    </MotionConfig>
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
