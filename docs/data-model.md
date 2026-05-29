# Data Model

> Updated for the cost-minimizing, never-zero-result design: the queue is now
> **persistent** (survives restarts and limit windows), provider budget/cost is
> tracked, and topics commit independently. SQLite is opened with
> `PRAGMA journal_mode=WAL`. Items marked `<!-- inferred -->` are reconstructed.

## Entity overview

```
Subject ─1──┬──< Chapter ─1──┬──< Topic ─1──┬──< Note
            │                │              ├──< MCQ
            │                │              ├──< Flashcard
            │                │              ├──< Formula
            │                │              └──< SourcePage
            │                └──< (chapter belongs to subject)
            └──< (subject is the top of the hierarchy)

Document ─1──< Chapter
Topic ─1──< ScheduleEntry
Topic ─1──< QueueJob               (persistent processing state)
ProviderState (one row per provider — budget/cost telemetry)
Settings (single row)
```

## Entities

### Subject
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | text | |
| accent_color | text | optional per-subject color <!-- inferred --> |
| exam_date | date | nullable; drives scheduler deadline mode |
| created_at | datetime | |

### Document
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| subject_id | int FK → Subject | |
| filename | text | |
| file_hash | text | cache key for markdown + page renders |
| markdown_path | text | cached markitdown output |
| status | enum | `uploaded` / `processing` / `ready` / `error` |
| uploaded_at | datetime | |

### Chapter
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| document_id | int FK → Document | |
| subject_id | int FK → Subject | denormalized for query speed; keep consistent with the parent document's subject on every write <!-- inferred --> |
| title | text | editable in structure review |
| order_index | int | |

### Topic
The atomic unit of processing **and** the transaction boundary for results.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| chapter_id | int FK → Chapter | |
| title | text | |
| priority | enum | `exam_critical` / `medium` / `skip` (skip = never sent to a model) |
| status | enum | `queued` / `processing` / `ready` / `error` |
| studied | bool | manual binary progress |
| order_index | int | |

### QueueJob
Persistent processing state so the queue survives app restarts and limit windows.
A job is created per topic to be processed.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| stage | enum | `formula` / `notes` / `assessment` — sub-steps committed independently |
| state | enum | `pending` / `running` / `done` / `failed` |
| attempts | int | retry counter; → `error` after N |
| assigned_provider | text | which waterfall provider ran/runs it |
| est_tokens | int | running estimate used for budget dispatch |
| last_error | text | nullable, for the retry UI |
| resume_after | datetime | nullable; set when a provider limit defers the job |
| created_at / updated_at | datetime | |

> Splitting a topic's job into `formula` / `notes` / `assessment` sub-stages means
> even within a topic, completed work (e.g. notes) is committed before the next
> sub-stage runs — reinforcing never-zero-result. <!-- inferred: sub-stage granularity -->

### ProviderState
One row per provider in the waterfall — live budget and accumulated cost.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| provider | text | `gemini_free` / `claude_paid` / `ollama` / ... |
| enabled | bool | user can hard-disable (e.g. never spend on paid) |
| order_index | int | waterfall position (cheapest first) |
| headroom | int | last probed remaining quota/tokens |
| reset_at | datetime | when a consumed window reopens (e.g. Claude 5h) |
| supports_vision | bool | gate for the formula stage |
| total_cost | float | accumulated $ spend (paid providers) |
| total_tokens | int | accumulated usage |

### Note
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| content_md | text | TipTap/markdown body |
| is_manual | bool | AI note vs. user-added block |
| locked | bool | prevents regeneration |
| stale | bool | set true when notes regenerated and assessment not yet re-run |
| created_at | datetime | |

### MCQ
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| question | text | |
| options | json | array of choices |
| correct_index | int | |
| explanation | text | |
| is_manual | bool | |

### Flashcard (SM-2 state)
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| front / back | text | |
| is_manual | bool | |
| ease_factor | float | SM-2, default 2.5 |
| interval | int | days until next review |
| repetitions | int | consecutive correct count |
| due_date | date | next review |

### Formula
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| note_id | int FK → Note | |
| latex | text | vision-model transcription |
| state | enum | `reconstructed` / `verified` |
| confidence | float | from vision model; low surfaces first <!-- inferred --> |
| bbox | json | crop region on the source page |

### SourcePage
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| page_number | int | |
| image_path | text | cached rendered page (for formula crops) |

### ScheduleEntry
| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| topic_id | int FK → Topic | |
| date | date | |
| is_revision_buffer | bool | distinct buffer day |
| source | enum | `sm2` / `manual` / `deadline` <!-- inferred --> |

### Settings (single row)
| Field | Type | Notes |
|---|---|---|
| id | int PK | always 1 |
| api_key_gemini | text | masked |
| api_key_claude | text | masked |
| allow_paid | bool | hard "never spend" switch; false = free-only waterfall |
| provider_order | json | overrides default cheapest-first order |
| ollama_enabled | bool | include local model in waterfall |
| pomodoro_work_min / break_min | int | |
| theme / accent_color / font_family / font_size | text/int | appearance |
