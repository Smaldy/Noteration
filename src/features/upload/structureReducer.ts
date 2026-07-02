import type {
  ChapterQueueState,
  ConfirmStructureIn,
  ProposedStructure,
  TopicPriority,
} from "@/types/structure";

/** Editable tree node with a stable local uid (React key + edit targeting). */
export interface EditTopic {
  uid: number;
  title: string;
  priority: TopicPriority;
  /** 1-indexed PDF pages backing this topic (slide decks); null when unmapped. */
  pages: number[] | null;
}

export interface EditChapter {
  uid: number;
  title: string;
  topics: EditTopic[];
  /** Per-chapter lane the user toggles. Defaults to running (pause to skip). */
  queueState: ChapterQueueState;
  /** Outline-backed page range, or null for non-outline trees. */
  pageStart: number | null;
  pageEnd: number | null;
}

/** A chapter is auto-skipped when every one of its topics is `skip` (trash). */
export function isChapterSkipped(chapter: EditChapter): boolean {
  return (
    chapter.topics.length > 0 && chapter.topics.every((t) => t.priority === "skip")
  );
}

export interface EditState {
  chapters: EditChapter[];
  nextUid: number;
}

export type EditAction =
  | { type: "init"; structure: ProposedStructure }
  | { type: "setChapterTitle"; cuid: number; title: string }
  | { type: "setChapterQueueState"; cuid: number; state: ChapterQueueState }
  | { type: "addChapter" }
  | { type: "removeChapter"; cuid: number }
  | { type: "setTopicTitle"; cuid: number; tuid: number; title: string }
  | { type: "setTopicPriority"; cuid: number; tuid: number; priority: TopicPriority }
  | { type: "addTopic"; cuid: number }
  | { type: "removeTopic"; cuid: number; tuid: number }
  | { type: "mergeTopicUp"; cuid: number; tuid: number };

export const emptyEditState: EditState = { chapters: [], nextUid: 1 };

/** Build editable state from a detected structure.

 * Topic priorities come from the backend (it pre-sets `skip` on trash chapters);
 * chapters carry their outline page range and default to `running` — confirming
 * processes the document; the student can pause specific chapters to skip them. */
export function initEditState(structure: ProposedStructure): EditState {
  let uid = 1;
  const chapters = structure.chapters.map((chapter) => ({
    uid: uid++,
    title: chapter.title,
    queueState: "running" as ChapterQueueState,
    pageStart: chapter.page_start,
    pageEnd: chapter.page_end,
    topics: chapter.topics.map((topic) => ({
      uid: uid++,
      title: topic.title,
      priority: topic.priority ?? ("medium" as TopicPriority),
      pages: topic.pages ?? null,
    })),
  }));
  return { chapters, nextUid: uid };
}

function mapChapter(
  state: EditState,
  cuid: number,
  fn: (c: EditChapter) => EditChapter,
): EditState {
  return {
    ...state,
    chapters: state.chapters.map((c) => (c.uid === cuid ? fn(c) : c)),
  };
}

export function structureReducer(state: EditState, action: EditAction): EditState {
  switch (action.type) {
    case "init":
      return initEditState(action.structure);

    case "setChapterTitle":
      return mapChapter(state, action.cuid, (c) => ({ ...c, title: action.title }));

    case "setChapterQueueState":
      return mapChapter(state, action.cuid, (c) => ({
        ...c,
        queueState: action.state,
      }));

    case "addChapter":
      return {
        ...state,
        nextUid: state.nextUid + 2,
        chapters: [
          ...state.chapters,
          {
            uid: state.nextUid,
            title: "",
            queueState: "running",
            pageStart: null,
            pageEnd: null,
            topics: [
              { uid: state.nextUid + 1, title: "", priority: "medium", pages: null },
            ],
          },
        ],
      };

    case "removeChapter":
      return {
        ...state,
        chapters: state.chapters.filter((c) => c.uid !== action.cuid),
      };

    case "setTopicTitle":
      return mapChapter(state, action.cuid, (c) => ({
        ...c,
        topics: c.topics.map((t) =>
          t.uid === action.tuid ? { ...t, title: action.title } : t,
        ),
      }));

    case "setTopicPriority":
      return mapChapter(state, action.cuid, (c) => ({
        ...c,
        topics: c.topics.map((t) =>
          t.uid === action.tuid ? { ...t, priority: action.priority } : t,
        ),
      }));

    case "addTopic":
      return {
        ...mapChapter(state, action.cuid, (c) => ({
          ...c,
          topics: [
            ...c.topics,
            { uid: state.nextUid, title: "", priority: "medium", pages: null },
          ],
        })),
        nextUid: state.nextUid + 1,
      };

    case "removeTopic":
      return mapChapter(state, action.cuid, (c) => ({
        ...c,
        topics: c.topics.filter((t) => t.uid !== action.tuid),
      }));

    case "mergeTopicUp":
      // Fold a topic into the one above it: the survivor keeps its title and
      // absorbs the merged topic's pages, so its notes cover both slides' text.
      return mapChapter(state, action.cuid, (c) => {
        const index = c.topics.findIndex((t) => t.uid === action.tuid);
        if (index <= 0) return c;
        const above = c.topics[index - 1];
        const merged = c.topics[index];
        const union = [
          ...new Set([...(above.pages ?? []), ...(merged.pages ?? [])]),
        ].sort((a, b) => a - b);
        return {
          ...c,
          topics: [
            ...c.topics.slice(0, index - 1),
            { ...above, pages: union.length ? union : null },
            ...c.topics.slice(index + 1),
          ],
        };
      });

    default:
      return state;
  }
}

/** True when every chapter has a title + ≥1 topic, and every topic has a title. */
export function isConfirmable(state: EditState): boolean {
  if (state.chapters.length === 0) return false;
  return state.chapters.every(
    (c) =>
      c.title.trim().length > 0 &&
      c.topics.length > 0 &&
      c.topics.every((t) => t.title.trim().length > 0),
  );
}

/** Topics that will actually be generated now: non-skip topics in RUNNING (or
 * overnight) chapters. A paused chapter's topics exist but won't process until
 * the user resumes it, so they don't count toward the pre-flight estimate. */
export function generatableTopicCount(state: EditState): number {
  return state.chapters.reduce((sum, c) => {
    if (c.queueState === "paused") return sum;
    return sum + c.topics.filter((t) => t.priority !== "skip").length;
  }, 0);
}

/** Project the editable tree into the confirm payload (trims titles). */
export function toConfirmPayload(
  state: EditState,
  examDate: string | null,
): ConfirmStructureIn {
  return {
    chapters: state.chapters.map((c) => ({
      title: c.title.trim(),
      queue_state: c.queueState,
      page_start: c.pageStart,
      page_end: c.pageEnd,
      topics: c.topics.map((t) => ({
        title: t.title.trim(),
        priority: t.priority,
        pages: t.pages,
      })),
    })),
    exam_date: examDate,
  };
}
