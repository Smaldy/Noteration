import { Navigate, Route, Routes } from "react-router-dom";

import { LibraryPage } from "@/features/library/LibraryPage";

// App shell + routing. Library is the home screen (Phase 9b); Upload, Study,
// Calendar, Queue, and Settings routes arrive in later Phase-9 sub-waves.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LibraryPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
