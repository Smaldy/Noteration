import { Bookmark, FileText, Layers } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  BackLink,
  EmptyState,
  PageHeader,
  PageShell,
  SectionLabel,
} from "@/components/PageShell";
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
    <PageShell width="narrow">
      <BackLink />

      <PageHeader
        icon={<Bookmark className="size-7 fill-primary text-primary" />}
        title={t("bookmarks.title")}
        subtitle={t("bookmarks.subtitle")}
      />

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      )}
      {status === "error" && <p className="text-sm text-destructive">{error}</p>}

      {empty && (
        <EmptyState
          icon={Bookmark}
          title={t("bookmarks.emptyTitle")}
          description={t("bookmarks.emptyDesc")}
        />
      )}

      {data && data.subjects.length > 0 && (
        <section className="mb-8">
          <SectionLabel>{t("bookmarks.subjects")}</SectionLabel>
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
                    className="rounded-sm transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
          <SectionLabel>{t("bookmarks.topics")}</SectionLabel>
          <ul className="space-y-2">
            {data.topics.map((t) => (
              <li key={t.id}>
                <div className="group flex items-center gap-3 rounded-xl border bg-card/70 p-3 shadow-sm transition-colors hover:border-ring/40">
                  <button
                    type="button"
                    onClick={() => navigate(`/documents/${t.document_id}/study/${t.id}`)}
                    className="flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
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
    </PageShell>
  );
}
