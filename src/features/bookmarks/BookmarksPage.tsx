import { ArrowLeft, Bookmark, FileText, Layers } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import { useBookmarksStore } from "@/stores/bookmarks";

import { BookmarkButton } from "./BookmarkButton";

export function BookmarksPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data, status, error, fetchBookmarks } = useBookmarksStore();

  useEffect(() => {
    void fetchBookmarks();
  }, [fetchBookmarks]);

  async function unbookmarkSubject(id: number) {
    await api.put(`/subjects/${id}/bookmark`, { bookmarked: false });
    await fetchBookmarks();
  }

  async function unbookmarkTopic(id: number) {
    await api.put(`/topics/${id}/bookmark`, { bookmarked: false });
    await fetchBookmarks();
  }

  const empty =
    status === "loaded" &&
    data &&
    data.subjects.length === 0 &&
    data.topics.length === 0;

  return (
    <div className="mx-auto max-w-3xl animate-rise px-6 py-10">
      <button
        type="button"
        data-arcade-sector="library"
        onClick={() => navigate("/")}
        className="mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t("common.library")}
      </button>

      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
          <Bookmark className="size-7 fill-primary text-primary" />
          {t("bookmarks.title")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("bookmarks.subtitle")}
        </p>
      </div>

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      )}
      {status === "error" && <p className="text-sm text-destructive">{error}</p>}

      {empty && (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed py-20 text-center">
          <Bookmark className="mb-4 size-10 text-muted-foreground" />
          <h2 className="text-lg font-medium">{t("bookmarks.emptyTitle")}</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            {t("bookmarks.emptyDesc")}
          </p>
        </div>
      )}

      {data && data.subjects.length > 0 && (
        <section className="mb-8">
          <h2 className="font-display mb-3 text-xs font-bold uppercase tracking-[0.12em] text-primary">
            {t("bookmarks.subjects")}
          </h2>
          <div className="flex flex-wrap gap-2">
            {data.subjects.map((s) => (
              <span
                key={s.id}
                className="inline-flex items-center gap-2 rounded-full border bg-card/70 py-1.5 pl-4 pr-2 text-sm font-medium shadow-sm transition-colors hover:border-ring/40"
              >
                {s.document_id != null ? (
                  <button
                    type="button"
                    onClick={() => navigate(`/documents/${s.document_id}/study`)}
                    className="transition-colors hover:text-primary"
                  >
                    {s.name}
                  </button>
                ) : (
                  s.name
                )}
                <BookmarkButton
                  bookmarked
                  label={s.name}
                  size="sm"
                  onToggle={() => void unbookmarkSubject(s.id)}
                />
              </span>
            ))}
          </div>
        </section>
      )}

      {data && data.topics.length > 0 && (
        <section>
          <h2 className="font-display mb-3 text-xs font-bold uppercase tracking-[0.12em] text-primary">
            {t("bookmarks.topics")}
          </h2>
          <ul className="space-y-2">
            {data.topics.map((t) => (
              <li key={t.id}>
                <div className="group flex items-center gap-3 rounded-xl border bg-card/70 p-3 shadow-sm transition-colors hover:border-ring/40">
                  <button
                    type="button"
                    onClick={() => navigate(`/documents/${t.document_id}/study/${t.id}`)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-soft-foreground">
                      <FileText className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{t.title}</span>
                      <span className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                        <Layers className="size-3" />
                        {t.subject_name} · {t.chapter_title}
                      </span>
                    </span>
                  </button>
                  <BookmarkButton
                    bookmarked
                    label={t.title}
                    onToggle={() => void unbookmarkTopic(t.id)}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
