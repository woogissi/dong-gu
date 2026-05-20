import unittest

from bs4 import BeautifulSoup

from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.ingestion.chunker import DocumentChunker


class ChunkerAndIpsiParserTest(unittest.TestCase):
    def test_ipsi_parser_prefers_title_hint(self) -> None:
        parser = IpsiNoticeParser()
        soup = BeautifulSoup("<html><title>fallback</title></html>", "html.parser")

        self.assertEqual(parser.find_title(soup, title_hint="입학 공지"), "입학 공지")

    def test_chunker_splits_attachment_sections(self) -> None:
        chunker = DocumentChunker(max_chars=120, overlap_chars=20)
        doc = {
            "doc_id": "doc1",
            "version": 1,
            "source_type": "notice",
            "title": "공지",
            "source_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=view&articleNo=1",
            "attachment_text": (
                "[ATTACHMENT: a.pdf]\n"
                "첫 번째 첨부 본문입니다. 장학 신청 일정과 제출 서류 안내가 포함되어 있습니다.\n\n"
                "[ATTACHMENT: b.pdf]\n"
                "두 번째 첨부 본문입니다. 수강 신청 절차와 유의사항 안내가 포함되어 있습니다."
            ),
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual([chunk["section_title"] for chunk in chunks], ["a.pdf", "b.pdf"])
        self.assertTrue(all(chunk["section_type"] == "attachment" for chunk in chunks))

    def test_chunk_hash_uses_normalized_text(self) -> None:
        chunker = DocumentChunker()

        first_hash = chunker.make_chunk_hash("PDF   다운로드\n\nNOTICE |||")
        second_hash = chunker.make_chunk_hash("pdf 다운로드 NOTICE |")

        self.assertEqual(first_hash, second_hash)

    def test_chunker_skips_short_stub_chunks(self) -> None:
        chunker = DocumentChunker()
        doc = {
            "doc_id": "doc-stub",
            "version": 1,
            "source_type": "static_page",
            "title": "센터 메인",
            "normalize": "PDF 다운로드",
        }

        self.assertEqual(chunker.chunk_document(doc), [])

    def test_chunker_keeps_meaningful_short_chunks(self) -> None:
        chunker = DocumentChunker()
        doc = {
            "doc_id": "doc-contact",
            "version": 1,
            "source_type": "notice",
            "title": "문의처",
            "normalize": "문의: 장학지원팀 051-890-1234",
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual(len(chunks), 1)
        self.assertIn("051-890-1234", chunks[0]["content"])

    def test_chunker_adds_paragraph_overlap_when_enabled(self) -> None:
        chunker = DocumentChunker(max_chars=60, paragraph_overlap_chars=15)
        first = "첫 번째 문단입니다. 장학 신청 일정과 제출 서류 안내가 포함되어 있습니다."
        second = "두 번째 문단입니다. 접수 기간과 담당 부서 연락처를 안내합니다."

        chunks = chunker.split_section_into_chunks(f"{first}\n\n{second}")

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[1].startswith(chunker.build_paragraph_overlap(first)))

    def test_chunker_prefers_structured_sections(self) -> None:
        chunker = DocumentChunker()
        doc = {
            "doc_id": "static-admin",
            "version": 1,
            "source_type": "institution",
            "title": "행정기관",
            "source_url": "https://www.deu.ac.kr/www/deu-administration-office.do",
            "normalize": "납작한 본문은 구조화 섹션이 있으면 청킹에 쓰지 않는다.",
            "structured_sections": [
                {
                    "section_type": "body",
                    "section_title": "교무처 > 교육혁신원",
                    "text": "상위조직: 교무처\n기관: 교육혁신원\n업무: 교육혁신 업무를 담당한다.\n전화번호: 051-890-4373",
                    "metadata": {"structure_type": "administration_office"},
                }
            ],
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["section_title"], "교무처 > 교육혁신원")
        self.assertIn("기관: 교육혁신원", chunks[0]["content"])
        self.assertNotIn("납작한 본문", chunks[0]["content"])
        self.assertEqual(
            chunks[0]["metadata"]["source_section_metadata"]["structure_type"],
            "administration_office",
        )

    def test_chunker_keeps_attachment_sections_when_structured_sections_exist(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        doc = {
            "doc_id": "static-sub0301",
            "version": 1,
            "source_type": "department",
            "title": "이수표",
            "source_url": "https://swcc.deu.ac.kr/computer/sub03_01.do",
            "structured_sections": [
                {
                    "section_type": "body",
                    "section_title": "content",
                    "text": (
                        "본문 안내가 충분히 길게 들어있어서 하나의 body chunk가 생성됩니다. "
                        "교육과정 이수표 원본 PDF를 함께 확인해야 정확한 학년별 교과목 정보를 알 수 있습니다."
                    ),
                    "metadata": {"structure_type": "generic_dom"},
                }
            ],
            "attachment_text": (
                "[ATTACHMENT: 원본파일 Download]\n"
                "| 학년 | 이수구분 | 교과목명 |\n"
                "| --- | --- | --- |\n"
                "| 2 | 전공필수 | 자료구조 |"
            ),
            "metadata": {
                "attachments": [
                    {
                        "file_name": "원본파일 Download",
                        "file_url": "https://swcc.deu.ac.kr/computer/sub03_01.do?mode=download&articleNo=83206&attachNo=129221",
                        "file_hash_sha256": "abc123",
                        "page_count": 1,
                        "table_count": 1,
                    }
                ]
            },
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual([chunk["section_type"] for chunk in chunks], ["body", "attachment"])
        attachment_chunk = chunks[1]
        self.assertEqual(attachment_chunk["section_title"], "원본파일 Download")
        self.assertEqual(
            attachment_chunk["metadata"]["source_section_metadata"]["file_hash_sha256"],
            "abc123",
        )
        self.assertIn("| 학년 | 이수구분 | 교과목명 |", attachment_chunk["content"])

    def test_chunker_excludes_binary_like_attachment_sections(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        doc = {
            "doc_id": "doc-binary-attachment",
            "version": 1,
            "source_type": "notice",
            "title": "Attachment notice",
            "normalize": "Normal body text with enough words to make a useful body chunk for retrieval.",
            "attachment_text": (
                "[ATTACHMENT: bad.pdf]\n"
                "%PDF-1.7\nstream\nendobj\nxref\n%%EOF"
            ),
        }

        chunks = chunker.chunk_document(doc)

        self.assertEqual([chunk["section_type"] for chunk in chunks], ["body"])
        self.assertEqual(doc["metadata"]["quality_skips"][0]["quality_status"], "binary_blocked")

    def test_short_chunk_quality_keeps_contact_schedule_money_and_place(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        samples = [
            "문의: 학생지원팀 051-890-1234",
            "신청기간: 2026.03.01 ~ 2026.03.15",
            "장학금 금액: 1,000,000원",
            "학과사무실 위치: 공학관 315호",
            "운영시간: 평일 09:00~18:00",
            "이메일: student@example.ac.kr",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                score = chunker.short_chunk_quality_score(sample)
                self.assertEqual(score["decision"], "keep")
                self.assertTrue(score["meaningful_signals"])
                self.assertTrue(chunker.is_meaningful_short_chunk(sample))

    def test_short_chunk_quality_drops_navigation_board_and_share_shells(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        samples = [
            "HOME > 게시판 > 공지사항",
            "번호 제목 작성자 작성일 조회수",
            "로그인 회원가입 사이트맵",
            "페이스북 트위터 공유",
            "이전글 다음글",
            "검색어를 입력하세요",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                score = chunker.short_chunk_quality_score(sample)
                self.assertEqual(score["decision"], "drop")
                self.assertTrue(score["noise_signals"])
                self.assertTrue(chunker.is_stub_chunk(sample))

    def test_chunker_keeps_meaningful_short_sections_but_drops_shell_sections(self) -> None:
        chunker = DocumentChunker(max_chars=500)
        doc = {
            "doc_id": "doc-short-quality",
            "version": 1,
            "source_type": "notice",
            "title": "짧은 정보",
            "structured_sections": [
                {"section_type": "body", "section_title": "nav", "text": "HOME > 게시판 > 공지사항"},
                {"section_type": "body", "section_title": "contact", "text": "문의: 학생지원팀 051-890-1234"},
                {"section_type": "body", "section_title": "period", "text": "신청기간: 2026.03.01 ~ 2026.03.15"},
                {"section_type": "body", "section_title": "amount", "text": "장학금 금액: 1,000,000원"},
            ],
        }

        chunks = chunker.chunk_document(doc)

        contents = "\n".join(chunk["content"] for chunk in chunks)
        self.assertNotIn("HOME > 게시판", contents)
        self.assertIn("051-890-1234", contents)
        self.assertIn("2026.03.01", contents)
        self.assertIn("1,000,000원", contents)
