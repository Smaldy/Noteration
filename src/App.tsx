import { Navigate, Route, Routes } from "react-router-dom";

import { LibraryPage } from "@/features/library/LibraryPage";
import { QueuePage } from "@/features/queue/QueuePage";
import { StudyPage } from "@/features/study/StudyPage";
import { StructureReviewPage } from "@/features/upload/StructureReviewPage";

// App shell + routing. Library is the home screen (Phase 9b); structure review
// is the upload gate (Phase 9c); study view is Phase 9d; queue is Phase 9e.
// Calendar and Settings routes arrive in later Phase-9 sub-waves.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LibraryPage />} />
      <Route path="/queue" element={<QueuePage />} />
      <Route path="/documents/:id/review" element={<StructureReviewPage />} />
      <Route path="/documents/:id/study" element={<StudyPage />} />
      <Route path="/documents/:id/study/:topicId" element={<StudyPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
