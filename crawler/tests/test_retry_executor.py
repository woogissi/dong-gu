import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from crawler.run import run_retry_failed_documents as retry_mod
from crawler.run.run_retry_failed_documents import RetryTarget, process_retry_targets


class FakeStateStore:
    def __init__(self) -> None:
        self.done = []
        self.failed = []
        self.unknown = []

    def mark_retry_done(self, retry_id: int) -> None:
        self.done.append(retry_id)

    def mark_retry_failed(self, retry_id: int, error: Exception) -> None:
        self.failed.append((retry_id, str(error)))

    def mark_unknown_task_type(self, retry_id: int, task_type: str) -> None:
        self.unknown.append((retry_id, task_type))


def target(task_type: str, **overrides) -> RetryTarget:
    data = {
        "id": 1,
        "queue_id": 1,
        "stage": task_type,
        "task_type": task_type,
        "source_type": "notice",
        "doc_id": "doc1",
        "url": "https://www.deu.ac.kr/doc",
        "error_type": None,
        "error_message": None,
        "reason": "test",
        "payload": {},
    }
    data.update(overrides)
    return RetryTarget.from_row(data)


class RetryExecutorTest(unittest.TestCase):
    def test_registry_marks_success_and_failure(self) -> None:
        state_store = FakeStateStore()
        ok = Mock()
        fail = Mock(side_effect=RuntimeError("boom"))

        with patch.dict(retry_mod.HANDLER_REGISTRY, {"ok_task": ok, "fail_task": fail}, clear=True):
            process_retry_targets(
                [target("ok_task"), target("fail_task", id=2, queue_id=2)],
                execute=True,
                state_store=state_store,
            )

        self.assertEqual(state_store.done, [1])
        self.assertEqual(state_store.failed, [(2, "boom")])

    def test_unknown_task_type_is_recorded(self) -> None:
        state_store = FakeStateStore()

        process_retry_targets([target("mystery")], execute=True, state_store=state_store)

        self.assertEqual(state_store.unknown, [(1, "mystery")])

    def test_chunking_handler_uses_curated_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            curated = Path(tmpdir) / "doc.json"
            curated.write_text('{"doc_id":"doc1","source_type":"notice","normalize":"본문"}', encoding="utf-8")

            with patch.object(retry_mod, "chunk_curated_file", return_value=Path(tmpdir) / "chunks.json") as mocked:
                retry_mod.handle_chunking(target("chunking", file_path=str(curated)))

        mocked.assert_called_once_with(curated)

    def test_attachment_download_handler_builds_payload_attachment(self) -> None:
        downloader = Mock()
        with patch("crawler.extractors.attachment_downloader.AttachmentDownloader", return_value=downloader):
            retry_mod.handle_attachment_download(
                target(
                    "attachment_download",
                    url="https://www.deu.ac.kr/file.pdf",
                    payload={"file_name": "guide.pdf", "attachment_index": 3},
                )
            )

        downloader.download.assert_called_once()
        _source_type, _doc_id, attachment = downloader.download.call_args.args
        self.assertEqual(attachment["file_name"], "guide.pdf")
        self.assertEqual(attachment["attachment_index"], 3)

    def test_file_parse_handler_requires_text(self) -> None:
        router = Mock()
        router.extract_text.return_value = {"attachment_text": "본문"}
        with patch("crawler.parsers.file_text_router.FileTextRouter", return_value=router):
            retry_mod.handle_file_parse(target("file_parse", file_path="file.pdf"))

        router.extract_text.assert_called_once_with("file.pdf")

    def test_static_board_and_vector_handlers_delegate(self) -> None:
        with patch.object(retry_mod, "process_static_seed") as process_static:
            retry_mod.handle_static_page(target("static_page"))
        self.assertTrue(process_static.call_args.args[0]["download_attachments"])

        with patch.object(retry_mod, "run_board_pipeline") as run_board:
            retry_mod.handle_board_list(target("board_list", payload={"pages": 2, "max_detail_count": 1}))
        run_board.assert_called_once()
        self.assertEqual(run_board.call_args.kwargs["pages"], 2)

        detail_extractor = Mock()
        detail_extractor.extract_detail.return_value = {
            "doc_id": "doc1",
            "source_type": "notice",
            "page_kind": "board_detail",
        }
        with patch("crawler.extractors.board_detail_extractor.BoardDetailExtractor", return_value=detail_extractor), patch(
            "crawler.run.run_full_pipeline.save_document_bundle"
        ) as save_bundle:
            retry_mod.handle_board_detail(target("board_detail", payload={"title_hint": "제목"}))
        save_bundle.assert_called_once()

        with patch.object(retry_mod, "vector_ingest_chunk_file") as vector_ingest, patch.object(
            retry_mod, "PGVectorLoader"
        ) as loader_cls, patch("crawler.ingestion.embed_worker.EmbeddingWorker"):
            loader = loader_cls.return_value
            loader.ensure_tables.return_value = None
            with TemporaryDirectory() as tmpdir:
                chunk_file = Path(tmpdir) / "chunks.json"
                chunk_file.write_text("[]", encoding="utf-8")
                retry_mod.handle_vector_ingestion(target("vector_ingestion", file_path=str(chunk_file)))
        vector_ingest.assert_called_once()


if __name__ == "__main__":
    unittest.main()
