import type {
  ConfirmStructureIn,
  ProposedStructure,
  TopicPriority,
} from "@/types/structure";

/** Editable tree node with a stable local uid (React key + edit targeting). */
export interface EditTopic {
  uid: number;
  title: string;
  priority: TopicPriority;
}

export interface EditChapter {
  uid: number;
  title: string;
  topics: EditTopic[];
}

export interface EditState {
  chapters: EditChapter[];
  nextUid: number;
}

export type EditAction =
  | { type: "init"; structure: ProposedStructure }
  | { type: "setChapterTitle"; cuid: number; title: string }
  | { type: "addChapter" }
  | { type: "removeChapter"; cuid: number }
  | { type: "setTopicTitle"; cuid: number; tuid: number; title: string }
  | { type: "setTopicPriority"; cuid: number; tuid: number; priority: TopicPriority }
  | { type: "addTopic"; cuid: number }
  | { type: "removeTopic"; cuid: number; tuid: number };

export const emptyEditState: EditState = { chapters: [], nextUid: 1 };

/** Build editable state from a detected structure (topics default to medium). */
export function initEditState(structure: ProposedStructure): EditState {
  let uid = 1;
  const chapters = structure.chapters.map((chapter) => ({
    uid: uid++,
    title: chapter.title,
    topics: chapter.topics.map((topic) => ({
      uid: uid++,
      title: topic.title,
      priority: "medium" as TopicPriority,
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

    case "addChapter":
      return {
        ...state,
        nextUid: state.nextUid + 2,
        chapters: [
          ...state.chapters,
          {
            uid: state.nextUid,
            title: "",
            topics: [
              { uid: state.nextUid + 1, title: "", priority: "medium" },
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
            { uid: state.nextUid, title: "", priority: "medium" },
          ],
        })),
        nextUid: state.nextUid + 1,
      };

    case "removeTopic":
      return mapChapter(state, action.cuid, (c) => ({
        ...c,
        topics: c.topics.filter((t) => t.uid !== action.tuid),
      }));

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

/** Number of topics that will actually be generated (non-skip). */
export function generatableTopicCount(state: EditState): number {
  return state.chapters.reduce(
    (sum, c) => sum + c.topics.filter((t) => t.priority !== "skip").length,
    0,
  );
}

/** Project the editable tree into the confirm payload (trims titles). */
export function toConfirmPayload(
  state: EditState,
  examDate: string | null,
): ConfirmStructureIn {
  return {
    chapters: state.chapters.map((c) => ({
      title: c.title.trim(),
      topics: c.topics.map((t) => ({ title: t.title.trim(), priority: t.priority })),
    })),
    exam_date: examDate,
  };
}
