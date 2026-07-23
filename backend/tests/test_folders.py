"""Folder service + HTTP tests.

Focus is on the parts that aren't expressible in the schema: the two-source
membership union, the two-level nesting cap, per-scope ordering, and the
delete semantics that must leave documents alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, Folder, FolderItem, Subject
from backend.models.enums import DocumentMode, DocumentStatus
from backend.services import folders as foldersvc
from backend.services.pipeline.ingestion import IngestionResult


def _subject_with_docs(session: Session, name: str, count: int = 2) -> Subject:
    subject = Subject(name=name)
    session.add(subject)
    session.flush()
    for i in range(count):
        document = Document(
            subject_id=subject.id,
            filename=f"{name.lower()}-{i}.pdf",
            file_hash=f"{name}{i}",
            status=DocumentStatus.ready,
            mode=DocumentMode.study,
        )
        session.add(document)
        session.flush()
        session.add(
            Chapter(document_id=document.id, subject_id=subject.id, title=f"Ch {i}")
        )
    session.commit()
    return subject


# --- membership --------------------------------------------------------------


def test_subject_tag_auto_includes_documents_without_rows(session: Session) -> None:
    subject = _subject_with_docs(session, "Psych", 2)
    folder = foldersvc.create_folder(session, name="Psych", subject_id=subject.id)

    contents = foldersvc.get_contents(session, folder.id)
    assert len(contents.documents) == 2
    # Auto membership is a query, not stored rows.
    assert session.query(FolderItem).count() == 0


def test_new_document_appears_in_tagged_folder(session: Session) -> None:
    subject = _subject_with_docs(session, "Chem", 1)
    folder = foldersvc.create_folder(session, name="Chem", subject_id=subject.id)
    assert len(foldersvc.get_contents(session, folder.id).documents) == 1

    session.add(
        Document(
            subject_id=subject.id,
            filename="new.pdf",
            file_hash="new",
            status=DocumentStatus.ready,
            mode=DocumentMode.study,
        )
    )
    session.commit()
    assert len(foldersvc.get_contents(session, folder.id).documents) == 2


def test_grouping_an_auto_member_does_not_duplicate_it(session: Session) -> None:
    """Filing a subject-tagged document into a group creates its FolderItem.

    The union must still yield one entry, not one per source.
    """
    subject = _subject_with_docs(session, "Bio", 2)
    folder = foldersvc.create_folder(session, name="Bio", subject_id=subject.id)
    group = foldersvc.create_group(session, folder.id, name="Exam 1", tint="lilac")
    doc_id = foldersvc.get_contents(session, folder.id).documents[0].id

    foldersvc.set_document_group(session, folder.id, doc_id, group.id)

    contents = foldersvc.get_contents(session, folder.id)
    assert len(contents.documents) == 2
    assert contents.document_groups[doc_id] == group.id


def test_copy_into_another_folder_shares_the_document(session: Session) -> None:
    subject = _subject_with_docs(session, "Math", 1)
    source = foldersvc.create_folder(session, name="Math", subject_id=subject.id)
    target = foldersvc.create_folder(session, name="Revision")
    doc_id = foldersvc.get_contents(session, source.id).documents[0].id

    foldersvc.add_documents(session, target.id, [doc_id])

    assert len(foldersvc.get_contents(session, source.id).documents) == 1
    assert len(foldersvc.get_contents(session, target.id).documents) == 1


def test_adding_the_same_document_twice_is_a_noop(session: Session) -> None:
    subject = _subject_with_docs(session, "Stats", 1)
    doc_id = subject.documents[0].id
    folder = foldersvc.create_folder(session, name="Loose")

    foldersvc.add_documents(session, folder.id, [doc_id])
    foldersvc.add_documents(session, folder.id, [doc_id])

    assert len(foldersvc.get_contents(session, folder.id).documents) == 1


def test_removing_a_manual_placement_keeps_auto_membership(session: Session) -> None:
    """A document that is both tagged-in and filed stays after the item is dropped."""
    subject = _subject_with_docs(session, "Physics", 1)
    folder = foldersvc.create_folder(session, name="Physics", subject_id=subject.id)
    group = foldersvc.create_group(session, folder.id, name="Week 1")
    doc_id = subject.documents[0].id
    foldersvc.set_document_group(session, folder.id, doc_id, group.id)

    foldersvc.remove_document(session, folder.id, doc_id)

    contents = foldersvc.get_contents(session, folder.id)
    assert [d.id for d in contents.documents] == [doc_id]
    assert contents.document_groups[doc_id] is None  # back to ungrouped


def test_list_counts_a_dual_source_document_once(session: Session) -> None:
    """A tagged-in document that is also filed into a group must not count twice."""
    subject = _subject_with_docs(session, "Neuro", 2)
    folder = foldersvc.create_folder(session, name="Neuro", subject_id=subject.id)
    group = foldersvc.create_group(session, folder.id, name="Exam 1")
    foldersvc.set_document_group(session, folder.id, subject.documents[0].id, group.id)

    listed = next(f for f in foldersvc.list_folders(session) if f.id == folder.id)
    assert listed.item_count == 2


def test_list_counts_loose_files(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Drop")
    foldersvc.add_file(
        session,
        folder.id,
        filename="a.pdf",
        content_type="application/pdf",
        data=b"%PDF fake",
    )
    listed = next(f for f in foldersvc.list_folders(session) if f.id == folder.id)
    assert listed.item_count == 1


def test_preview_ids_are_capped(session: Session) -> None:
    """The tray previews a few items; the rest collapse into "+N more"."""
    subject = _subject_with_docs(session, "Wide", 6)
    folder = foldersvc.create_folder(session, name="Wide", subject_id=subject.id)
    listed = next(f for f in foldersvc.list_folders(session) if f.id == folder.id)
    assert len(listed.preview_ids) == foldersvc.PREVIEW_LIMIT
    assert listed.item_count == 6


# --- main folder --------------------------------------------------------------


def test_first_tagged_folder_becomes_main(session: Session) -> None:
    """Unchanged behavior for the common one-folder-per-subject case."""
    subject = _subject_with_docs(session, "Solo", 2)
    folder = foldersvc.create_folder(session, name="Solo", subject_id=subject.id)
    assert folder.is_main is True
    assert len(foldersvc.get_contents(session, folder.id).documents) == 2


def test_second_folder_on_a_subject_does_not_duplicate_its_notes(
    session: Session,
) -> None:
    """The reported bug: two folders tagged to one subject each listed all of it."""
    subject = _subject_with_docs(session, "Dup", 3)
    main = foldersvc.create_folder(session, name="Main", subject_id=subject.id)
    other = foldersvc.create_folder(session, name="Side", subject_id=subject.id)

    assert other.is_main is False
    assert len(foldersvc.get_contents(session, main.id).documents) == 3
    assert foldersvc.get_contents(session, other.id).documents == []


def test_claiming_main_demotes_the_previous_holder(session: Session) -> None:
    subject = _subject_with_docs(session, "Move", 2)
    first = foldersvc.create_folder(session, name="First", subject_id=subject.id)
    second = foldersvc.create_folder(session, name="Second", subject_id=subject.id)

    foldersvc.update_folder(session, second.id, is_main=True)

    session.refresh(first)
    assert first.is_main is False
    assert foldersvc.get_contents(session, first.id).documents == []
    assert len(foldersvc.get_contents(session, second.id).documents) == 2


def test_new_notes_land_in_the_main_folder(session: Session) -> None:
    """The point of the flag: generated notes appear in one chosen folder."""
    subject = _subject_with_docs(session, "Land", 1)
    main = foldersvc.create_folder(session, name="Main", subject_id=subject.id)
    foldersvc.create_folder(session, name="Side", subject_id=subject.id)

    session.add(
        Document(
            subject_id=subject.id,
            filename="fresh.pdf",
            file_hash="fresh",
            status=DocumentStatus.ready,
            mode=DocumentMode.study,
        )
    )
    session.commit()

    assert len(foldersvc.get_contents(session, main.id).documents) == 2


def test_deleting_the_main_folder_hands_the_role_over(session: Session) -> None:
    subject = _subject_with_docs(session, "Hand", 2)
    main = foldersvc.create_folder(session, name="Main", subject_id=subject.id)
    other = foldersvc.create_folder(session, name="Side", subject_id=subject.id)

    foldersvc.delete_folder(session, main.id)

    session.refresh(other)
    assert other.is_main is True
    assert len(foldersvc.get_contents(session, other.id).documents) == 2


def test_untagging_clears_main(session: Session) -> None:
    subject = _subject_with_docs(session, "Untag", 1)
    folder = foldersvc.create_folder(session, name="Untag", subject_id=subject.id)
    updated = foldersvc.update_folder(session, folder.id, clear_subject=True)
    assert updated.is_main is False


# --- bookmarks ----------------------------------------------------------------


def test_folder_bookmark_round_trips(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Star")
    assert folder.bookmarked is False
    starred = foldersvc.set_folder_bookmark(session, folder.id, True)
    assert starred.bookmarked is True
    # Still decorated, so starring from the grid can't blank the tray.
    assert hasattr(starred, "item_count")


def test_note_bookmark_is_scoped_to_one_folder(session: Session) -> None:
    """The whole point of the sub-bookmark: starring here doesn't star there."""
    subject = _subject_with_docs(session, "Scope", 1)
    doc_id = subject.documents[0].id
    here = foldersvc.create_folder(session, name="Here", subject_id=subject.id)
    there = foldersvc.create_folder(session, name="There")
    foldersvc.add_documents(session, there.id, [doc_id])

    foldersvc.set_document_bookmark(session, here.id, doc_id, True)

    assert foldersvc.get_contents(session, here.id).document_bookmarks[doc_id] is True
    assert foldersvc.get_contents(session, there.id).document_bookmarks[doc_id] is False


def test_bookmarking_an_auto_member_materializes_its_row(session: Session) -> None:
    """Auto members are computed, so the flag needs a FolderItem to live on."""
    subject = _subject_with_docs(session, "Auto", 2)
    folder = foldersvc.create_folder(session, name="Auto", subject_id=subject.id)
    doc_id = subject.documents[0].id
    assert session.query(FolderItem).count() == 0

    foldersvc.set_document_bookmark(session, folder.id, doc_id, True)

    assert session.query(FolderItem).count() == 1
    contents = foldersvc.get_contents(session, folder.id)
    assert len(contents.documents) == 2  # not duplicated by the new row
    assert contents.document_bookmarks[doc_id] is True


def test_unstarring_keeps_the_note_in_the_folder(session: Session) -> None:
    subject = _subject_with_docs(session, "Keep", 1)
    folder = foldersvc.create_folder(session, name="Keep", subject_id=subject.id)
    doc_id = subject.documents[0].id

    foldersvc.set_document_bookmark(session, folder.id, doc_id, True)
    foldersvc.set_document_bookmark(session, folder.id, doc_id, False)

    contents = foldersvc.get_contents(session, folder.id)
    assert [d.id for d in contents.documents] == [doc_id]
    assert contents.document_bookmarks[doc_id] is False


# --- decoration ---------------------------------------------------------------


def test_update_returns_a_decorated_folder(session: Session) -> None:
    """Regression: create/update returned bare ORM rows, so item_count came back
    as 0 and the Library redrew the folder as empty after a recolor."""
    subject = _subject_with_docs(session, "Paint", 2)
    folder = foldersvc.create_folder(session, name="Paint", subject_id=subject.id)
    assert folder.item_count == 2  # type: ignore[attr-defined]

    recolored = foldersvc.update_folder(session, folder.id, tint="rose")

    assert recolored.item_count == 2  # type: ignore[attr-defined]
    assert len(recolored.preview_ids) == 2  # type: ignore[attr-defined]


# --- tint values --------------------------------------------------------------


def test_custom_hex_tint_is_kept(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Custom", tint="#A1B2C3")
    assert folder.tint == "#a1b2c3"


def test_malformed_hex_falls_back(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Bad", tint="#12345")
    assert folder.tint == "slate"


# --- nesting -----------------------------------------------------------------


def test_child_folder_is_allowed(session: Session) -> None:
    root = foldersvc.create_folder(session, name="Root")
    child = foldersvc.create_folder(session, name="Child", parent_id=root.id)
    assert child.parent_id == root.id


def test_third_level_is_rejected(session: Session) -> None:
    root = foldersvc.create_folder(session, name="Root")
    child = foldersvc.create_folder(session, name="Child", parent_id=root.id)
    with pytest.raises(foldersvc.FolderDepthError):
        foldersvc.create_folder(session, name="Grandchild", parent_id=child.id)


def test_folder_cannot_become_its_own_parent(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Solo")
    with pytest.raises(foldersvc.FolderDepthError):
        foldersvc.update_folder(session, folder.id, parent_id=folder.id)


def test_folder_with_children_cannot_be_nested(session: Session) -> None:
    """Nesting a parent would push its children to depth three."""
    root = foldersvc.create_folder(session, name="Root")
    foldersvc.create_folder(session, name="Child", parent_id=root.id)
    other = foldersvc.create_folder(session, name="Other")
    with pytest.raises(foldersvc.FolderDepthError):
        foldersvc.update_folder(session, root.id, parent_id=other.id)


# --- ordering ----------------------------------------------------------------


def test_order_index_increments_within_scope(session: Session) -> None:
    """Regression: `column == None` renders as `= NULL` (never true) and a max
    of 0 is falsy, both of which pinned every new folder to order_index 0."""
    first = foldersvc.create_folder(session, name="A")
    second = foldersvc.create_folder(session, name="B")
    third = foldersvc.create_folder(session, name="C")
    assert [first.order_index, second.order_index, third.order_index] == [0, 1, 2]


def test_child_ordering_is_scoped_to_its_parent(session: Session) -> None:
    root = foldersvc.create_folder(session, name="Root")  # order 0 among roots
    a = foldersvc.create_folder(session, name="A", parent_id=root.id)
    b = foldersvc.create_folder(session, name="B", parent_id=root.id)
    assert [a.order_index, b.order_index] == [0, 1]


# --- deletes -----------------------------------------------------------------


def test_deleting_a_folder_leaves_documents_alone(session: Session) -> None:
    subject = _subject_with_docs(session, "Geo", 2)
    folder = foldersvc.create_folder(session, name="Geo", subject_id=subject.id)
    foldersvc.add_documents(session, folder.id, [subject.documents[0].id])

    foldersvc.delete_folder(session, folder.id)

    assert session.query(Document).count() == 2
    assert session.query(FolderItem).count() == 0


def test_deleting_a_folder_removes_its_children(session: Session) -> None:
    root = foldersvc.create_folder(session, name="Root")
    foldersvc.create_folder(session, name="Child", parent_id=root.id)
    foldersvc.delete_folder(session, root.id)
    assert session.query(Folder).count() == 0


def test_deleting_a_subject_degrades_the_folder_to_manual(session: Session) -> None:
    """SET NULL, not CASCADE: the folder may still hold files the user added."""
    subject = _subject_with_docs(session, "Art", 1)
    folder = foldersvc.create_folder(session, name="Art", subject_id=subject.id)

    session.delete(subject)
    session.commit()
    session.expire_all()

    survivor = session.get(Folder, folder.id)
    assert survivor is not None
    assert survivor.subject_id is None


def test_deleting_a_group_keeps_its_contents(session: Session) -> None:
    subject = _subject_with_docs(session, "Econ", 1)
    folder = foldersvc.create_folder(session, name="Econ", subject_id=subject.id)
    group = foldersvc.create_group(session, folder.id, name="Midterm")
    doc_id = subject.documents[0].id
    foldersvc.set_document_group(session, folder.id, doc_id, group.id)

    foldersvc.delete_group(session, group.id)

    contents = foldersvc.get_contents(session, folder.id)
    assert [d.id for d in contents.documents] == [doc_id]
    assert contents.document_groups[doc_id] is None


# --- files -------------------------------------------------------------------


def test_add_file_accepts_pdf_and_image(session: Session, tmp_path) -> None:
    folder = foldersvc.create_folder(session, name="Drop")
    pdf = foldersvc.add_file(
        session,
        folder.id,
        filename="a.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4 fake",
    )
    image = foldersvc.add_file(
        session,
        folder.id,
        filename="b.png",
        content_type="image/png",
        data=b"\x89PNG fake",
    )
    assert (pdf.kind, image.kind) == ("pdf", "image")
    # Inert until explicitly promoted.
    assert pdf.generated_document_id is None


def test_add_file_rejects_other_types(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Drop")
    with pytest.raises(foldersvc.UnsupportedFolderFileError):
        foldersvc.add_file(
            session,
            folder.id,
            filename="notes.txt",
            content_type="text/plain",
            data=b"hello",
        )


def test_add_file_rejects_empty(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Drop")
    with pytest.raises(foldersvc.UnsupportedFolderFileError):
        foldersvc.add_file(
            session,
            folder.id,
            filename="a.pdf",
            content_type="application/pdf",
            data=b"",
        )


# --- generating notes from a loose file ---------------------------------------


def _fake_pdf() -> bytes:
    return b"%PDF-1.4\nfake body\n%%EOF\n"


def _fake_ingest(markdown_path: Path):
    """Stand-in for the real PDF pipeline; the folder tests care about the rows
    that get written, not about parsing a PDF."""

    def _ingest(pdf_path: Path) -> IngestionResult:
        return IngestionResult(
            file_hash="deadbeef",
            markdown="# Chapter 1\n## Topic\n",
            markdown_path=markdown_path,
            page_image_paths=[],
            page_count=1,
            is_scanned=False,
            from_cache=False,
        )

    return _ingest


def _promote_kwargs(tmp_path: Path) -> dict:
    md = tmp_path / "doc.md"
    md.write_text("# Chapter 1\n## Topic\n", encoding="utf-8")
    return {"ingest_fn": _fake_ingest(md), "uploads_dir": tmp_path / "uploads"}


def test_generate_notes_promotes_a_pdf(session: Session, tmp_path: Path) -> None:
    subject = _subject_with_docs(session, "Promo", 0)
    folder = foldersvc.create_folder(session, name="Promo", subject_id=subject.id)
    file = foldersvc.add_file(
        session,
        folder.id,
        filename="lecture.pdf",
        content_type="application/pdf",
        data=_fake_pdf(),
    )
    document = foldersvc.generate_notes(
        session, file.id, **_promote_kwargs(tmp_path)
    )

    assert document.subject_id == subject.id
    assert document.filename == "lecture.pdf"
    session.refresh(file)
    assert file.generated_document_id == document.id
    # It is placed in the folder, not merely created in the subject.
    assert (
        session.query(FolderItem)
        .filter_by(folder_id=folder.id, document_id=document.id)
        .count()
        == 1
    )


def test_generate_notes_is_idempotent(session: Session, tmp_path: Path) -> None:
    subject = _subject_with_docs(session, "Once", 0)
    folder = foldersvc.create_folder(session, name="Once", subject_id=subject.id)
    file = foldersvc.add_file(
        session,
        folder.id,
        filename="a.pdf",
        content_type="application/pdf",
        data=_fake_pdf(),
    )
    first = foldersvc.generate_notes(session, file.id, **_promote_kwargs(tmp_path))
    second = foldersvc.generate_notes(session, file.id, **_promote_kwargs(tmp_path))

    assert first.id == second.id
    assert session.query(Document).count() == 1


def test_promoted_file_is_hidden_from_contents(session: Session, tmp_path: Path) -> None:
    """The document represents it now; listing both would show it twice."""
    subject = _subject_with_docs(session, "Hide", 0)
    folder = foldersvc.create_folder(session, name="Hide", subject_id=subject.id)
    file = foldersvc.add_file(
        session,
        folder.id,
        filename="a.pdf",
        content_type="application/pdf",
        data=_fake_pdf(),
    )
    assert len(foldersvc.get_contents(session, folder.id).files) == 1

    foldersvc.generate_notes(session, file.id, **_promote_kwargs(tmp_path))

    contents = foldersvc.get_contents(session, folder.id)
    assert contents.files == []
    assert len(contents.documents) == 1


def test_generate_notes_needs_a_subject(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Untagged")  # no subject tag
    file = foldersvc.add_file(
        session,
        folder.id,
        filename="a.pdf",
        content_type="application/pdf",
        data=_fake_pdf(),
    )
    with pytest.raises(foldersvc.MissingSubjectError):
        foldersvc.generate_notes(session, file.id)


def test_generate_notes_rejects_images(session: Session) -> None:
    subject = _subject_with_docs(session, "Pic", 0)
    folder = foldersvc.create_folder(session, name="Pic", subject_id=subject.id)
    file = foldersvc.add_file(
        session,
        folder.id,
        filename="a.png",
        content_type="image/png",
        data=b"\x89PNG fake",
    )
    with pytest.raises(foldersvc.UnsupportedFolderFileError):
        foldersvc.generate_notes(session, file.id)


# --- tints -------------------------------------------------------------------


def test_unknown_tint_falls_back_to_neutral(session: Session) -> None:
    folder = foldersvc.create_folder(session, name="Odd", tint="chartreuse")
    assert folder.tint == "slate"


# --- HTTP --------------------------------------------------------------------


def test_folder_crud_over_http(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        subject = _subject_with_docs(db, "Neuro", 2)
        subject_id = subject.id

    created = client.post(
        "/api/folders", json={"name": "Neuro", "subject_id": subject_id, "tint": "sky"}
    )
    assert created.status_code == 201
    folder_id = created.json()["id"]

    listed = client.get("/api/folders").json()
    assert listed[0]["item_count"] == 2  # auto members counted

    contents = client.get(f"/api/folders/{folder_id}").json()
    assert len(contents["documents"]) == 2

    patched = client.patch(f"/api/folders/{folder_id}", json={"name": "Neuroanatomy"})
    assert patched.json()["name"] == "Neuroanatomy"

    assert client.delete(f"/api/folders/{folder_id}").status_code == 204
    assert client.get(f"/api/folders/{folder_id}").status_code == 404


def test_clear_subject_tag_over_http(
    client: TestClient, db_factory: sessionmaker
) -> None:
    """`null` means "leave alone", so untagging needs the explicit flag."""
    with db_factory() as db:
        subject = _subject_with_docs(db, "Hist", 1)
        subject_id = subject.id

    folder_id = client.post(
        "/api/folders", json={"name": "Hist", "subject_id": subject_id}
    ).json()["id"]

    # A bare null must NOT untag.
    client.patch(f"/api/folders/{folder_id}", json={"subject_id": None})
    assert (
        client.get(f"/api/folders/{folder_id}").json()["folder"]["subject_id"]
        == subject_id
    )

    client.patch(f"/api/folders/{folder_id}", json={"clear_subject": True})
    body = client.get(f"/api/folders/{folder_id}").json()
    assert body["folder"]["subject_id"] is None
    assert body["documents"] == []  # auto members drop away with the tag


def test_depth_error_returns_422(client: TestClient) -> None:
    root = client.post("/api/folders", json={"name": "Root"}).json()["id"]
    child = client.post(
        "/api/folders", json={"name": "Child", "parent_id": root}
    ).json()["id"]
    too_deep = client.post("/api/folders", json={"name": "Deep", "parent_id": child})
    assert too_deep.status_code == 422


def test_files_route_is_not_shadowed_by_folder_id(client: TestClient) -> None:
    """`/folders/files/...` must not be parsed as folder id "files"."""
    assert client.get("/api/folders/files/999/raw").status_code == 404
