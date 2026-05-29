import { useEffect, useState } from "react";

// Phase 1 placeholder: proves the served bundle can reach the FastAPI API.
// Real feature shell (Library, Upload, Study, ...) arrives in Phase 9.
export default function App() {
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data: { status: string }) => setHealth(data.status))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Noteration</h1>
      <p>Backend health: {health}</p>
    </main>
  );
}
