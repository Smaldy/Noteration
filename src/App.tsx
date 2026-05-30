import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { CalendarPage } from "@/features/calendar/CalendarPage";
import { LibraryPage } from "@/features/library/LibraryPage";
import { QueuePage } from "@/features/queue/QueuePage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StudyPage } from "@/features/study/StudyPage";
import { StructureReviewPage } from "@/features/upload/StructureReviewPage";
import { useSettingsStore } from "@/stores/settings";

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
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      >
        <Routes location={location}>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/documents/:id/review" element={<StructureReviewPage />} />
          <Route path="/documents/:id/study" element={<StudyPage />} />
          <Route path="/documents/:id/study/:topicId" element={<StudyPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}
