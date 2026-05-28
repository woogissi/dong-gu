import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.attachment_downloader import AttachmentDownloader
from crawler.extractors.static_page_extractor import StaticPageExtractor


class FakeStreamResponse:
    url = "https://www.deu.ac.kr/file.pdf"
    status_code = 200
    headers = {
        "Content-Type": "application/pdf",
        "Content-Length": "11",
        "Content-Disposition": 'attachment; filename="guide.pdf"',
    }

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield b"hello "
        yield b"world"


class DynamicDownloadResponse(FakeStreamResponse):
    url = "https://www.deu.ac.kr/www/deu-notice.do?mode=download&articleNo=123&attachNo=1"
    headers = {
        "Content-Type": "application/x-hwp",
        "Content-Length": "11",
        "Content-Disposition": 'attachment; filename="guide.hwp"',
    }


class QueryFilenameDownloadResponse(FakeStreamResponse):
    url = "https://ipsi.deu.ac.kr/file/download.do?sfn=server.bin&ofn=guide.pdf"
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": "11",
    }


class ContentTypeOnlyDownloadResponse(FakeStreamResponse):
    url = "https://www.deu.ac.kr/www/deu-notice.do?mode=download&articleNo=123&attachNo=1"
    headers = {
        "Content-Type": "application/pdf",
        "Content-Length": "11",
    }


class MagicBytesDownloadResponse(FakeStreamResponse):
    url = "https://www.deu.ac.kr/download"
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": "13",
    }

    def iter_content(self, chunk_size: int):
        yield b"%PDF-1.7 body"


class FailingOnceStreamResponse(FakeStreamResponse):
    attempts = 0

    def iter_content(self, chunk_size: int):
        type(self).attempts += 1
        if type(self).attempts == 1:
            yield b"partial "
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        yield b"hello "
        yield b"again"


class AttachmentAndStaticExtractorTest(unittest.TestCase):
    def test_attachment_downloader_uses_timeout_size_limit_and_saves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(
                base_save_dir=Path(tmpdir),
                max_file_size=1024,
                timeout=(1, 2),
            )
            downloader.session.get = Mock(return_value=FakeStreamResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "안내문",
                    "file_url": "https://www.deu.ac.kr/file.pdf",
                },
            )

            downloader.session.get.assert_called_once_with(
                "https://www.deu.ac.kr/file.pdf",
                timeout=(1, 2),
                stream=True,
            )
            self.assertEqual(downloaded["file_ext"], ".pdf")
            self.assertEqual(
                downloaded["file_hash_sha256"],
                "b94d27b9934d3e08a52e52d7da7dabfac484ef"
                "e37a5380ee9088f7ace2efcde9",
            )
            self.assertEqual(Path(downloaded["saved_path"]).read_bytes(), b"hello world")

    def test_attachment_downloader_ignores_dynamic_route_suffix_when_guessing_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(
                base_save_dir=Path(tmpdir),
                max_file_size=1024,
                timeout=(1, 2),
            )
            downloader.session.get = Mock(return_value=DynamicDownloadResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "deu-notice.do_mode=download&articleNo=123&attachNo=1",
                    "file_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=download&articleNo=123&attachNo=1",
                },
            )

            self.assertEqual(downloaded["file_ext"], ".hwp")
            self.assertTrue(downloaded["saved_path"].endswith(".hwp"))
            self.assertNotIn(".do_mode=download", downloaded["saved_path"])

    def test_attachment_downloader_restores_extension_from_query_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(base_save_dir=Path(tmpdir), max_file_size=1024, timeout=(1, 2))
            downloader.session.get = Mock(return_value=QueryFilenameDownloadResponse())

            downloaded = downloader.download(
                "admission",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "download",
                    "file_url": "https://ipsi.deu.ac.kr/file/download.do?sfn=server.bin&ofn=guide.pdf",
                },
            )

            self.assertEqual(downloaded["file_ext"], ".pdf")
            self.assertEqual(downloaded["extension_source"], "url_query")
            self.assertTrue(downloaded["saved_path"].endswith("guide.pdf"))

    def test_attachment_downloader_restores_extension_from_content_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(base_save_dir=Path(tmpdir), max_file_size=1024, timeout=(1, 2))
            downloader.session.get = Mock(return_value=ContentTypeOnlyDownloadResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "deu-notice.do_mode=download&articleNo=123&attachNo=1",
                    "file_url": "https://www.deu.ac.kr/www/deu-notice.do?mode=download&articleNo=123&attachNo=1",
                },
            )

            self.assertEqual(downloaded["file_ext"], ".pdf")
            self.assertEqual(downloaded["extension_source"], "content_type")
            self.assertTrue(downloaded["saved_path"].endswith(".pdf"))
            self.assertFalse(Path(downloaded["saved_path"]).name.startswith("deu-notice.do"))

    def test_attachment_downloader_uses_magic_bytes_when_headers_lack_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AttachmentDownloader(base_save_dir=Path(tmpdir), max_file_size=1024, timeout=(1, 2))
            downloader.session.get = Mock(return_value=MagicBytesDownloadResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 3,
                    "file_name": "download",
                    "file_url": "https://www.deu.ac.kr/download",
                },
            )

            self.assertEqual(downloaded["file_ext"], ".pdf")
            self.assertEqual(downloaded["extension_source"], "magic_bytes")
            self.assertTrue(downloaded["saved_path"].endswith(".pdf"))

    def test_attachment_downloader_decodes_rfc5987_filename(self) -> None:
        downloader = AttachmentDownloader()

        filename = downloader.extract_filename_from_content_disposition(
            "attachment; filename*=UTF-8''%EA%B0%80%EC%9D%B4%EB%93%9C.pdf"
        )

        self.assertEqual(filename, "가이드.pdf")

    def test_attachment_downloader_retries_chunked_encoding_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            FailingOnceStreamResponse.attempts = 0
            downloader = AttachmentDownloader(
                base_save_dir=Path(tmpdir),
                max_file_size=1024,
                timeout=(1, 2),
                max_download_attempts=2,
                retry_backoff_factor=0,
            )
            downloader.session.get = Mock(return_value=FailingOnceStreamResponse())

            downloaded = downloader.download(
                "notice",
                "doc1",
                {
                    "attachment_index": 1,
                    "file_name": "guide",
                    "file_url": "https://www.deu.ac.kr/file.pdf",
                },
            )

            self.assertEqual(downloader.session.get.call_count, 2)
            self.assertEqual(Path(downloaded["saved_path"]).read_bytes(), b"hello again")
            self.assertFalse(Path(downloaded["saved_path"] + ".part").exists())

    def test_static_page_extractor_collects_attachment_links(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <p>정적 안내 본문</p>
              <a href="/files/guide.pdf">안내 PDF</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/info.do",
                    "final_url": "https://www.deu.ac.kr/www/info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("campus", "https://www.deu.ac.kr/www/info.do")

        self.assertEqual(doc["attachments"][0]["file_name"], "안내 PDF")
        self.assertEqual(doc["attachments"][0]["file_url"], "https://www.deu.ac.kr/files/guide.pdf")

    def test_static_page_extractor_skips_do_view_links_as_attachments(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="/pluscenter/file.do?mode=view&articleNo=84614">attachment-like page</a>
              <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">download</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/info.do",
                    "final_url": "https://www.deu.ac.kr/www/info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("campus", "https://www.deu.ac.kr/www/info.do")

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
        self.assertNotIn("mode=view", doc["attachments"][0]["file_url"])

    def test_static_page_extractor_skips_social_profile_links_as_attachments(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="https://m.facebook.com/profile.php?id=1579580098940911/">student council</a>
              <a href="/www/deu-notice.do?mode=download&articleNo=123&attachNo=1">download</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/info.do",
                    "final_url": "https://www.deu.ac.kr/www/info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("campus", "https://www.deu.ac.kr/www/info.do")

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertIn("mode=download", doc["attachments"][0]["file_url"])
        self.assertNotIn("facebook", doc["attachments"][0]["file_url"].lower())

    def test_static_page_extractor_dedupes_same_attachment_url_with_different_labels(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="/computer/sub03_01.do?mode=download&articleNo=83206&attachNo=129221">원본파일 Download</a>
              <a href="/computer/sub03_01.do?mode=download&articleNo=83206&attachNo=129221"></a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"swcc.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://swcc.deu.ac.kr/computer/sub03_01.do",
                    "final_url": "https://swcc.deu.ac.kr/computer/sub03_01.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("department", "https://swcc.deu.ac.kr/computer/sub03_01.do")

        self.assertEqual(len(doc["attachments"]), 1)
        self.assertEqual(doc["attachments"][0]["attachment_index"], 1)
        self.assertEqual(doc["attachments"][0]["file_name"], "원본파일 Download")

    def test_static_page_extractor_uses_redirect_final_url_as_identity(self) -> None:
        html = """
        <html>
          <body>
            <header><a href="/koreanl/sub01_01.do">intro</a></header>
            <main><p>department body</p></main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"koreanl.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://koreanl.deu.ac.kr/",
                    "final_url": "https://koreanl.deu.ac.kr/koreanl/index.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("department", "https://koreanl.deu.ac.kr/")

        self.assertEqual(doc["source_url"], "https://koreanl.deu.ac.kr/koreanl/index.do")
        self.assertEqual(doc["doc_id"], extractor.make_doc_id("https://koreanl.deu.ac.kr/koreanl/index.do"))
        self.assertIn("https://koreanl.deu.ac.kr/koreanl/sub01_01.do", doc["outgoing_links"])

    def test_static_page_extractor_collects_department_links_from_ipsi_detail(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <a href="https://mse.deu.ac.kr">신소재공학부</a>
              <a href="https://example.com">external</a>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://ipsi.deu.ac.kr/universityDetail.do",
                    "final_url": "https://ipsi.deu.ac.kr/universityDetail.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("admission", "https://ipsi.deu.ac.kr/universityDetail.do")

        self.assertEqual(doc["outgoing_links"], ["https://mse.deu.ac.kr"])

    def test_static_main_page_filters_preview_ui_but_keeps_intro(self) -> None:
        html = """
        <html>
          <head><title>학생상담센터 | 동의대학교</title></head>
          <body>
            <header><a href="/counsel/sub01_01.do">센터소개</a></header>
            <main>
              <section class="center-greeting">
                <h2>학생상담센터</h2>
                <p>건강한 대학생활 적응과 성장을 위한 행복발전소입니다.</p>
                <p>개인상담과 심리검사를 통해 학생의 성장을 지원합니다.</p>
              </section>
              <section class="notice-list">
                <h3>NOTICE</h3>
                <button>게시물 좌측으로 이동</button>
                <button>게시물 우측으로 이동</button>
                <a href="/counsel/sub05_01.do?articleNo=1&mode=view">최신 공지 preview</a>
                <a>More</a>
              </section>
              <section class="program-list">
                <h3>PROGRAM</h3>
                <span>이전 정지 시작 다음</span>
                <p>2026학년도 집단상담 프로그램</p>
              </section>
              <section class="gallery">
                <h3>행사사진 More</h3>
                <p>행사사진 preview</p>
              </section>
              <section class="sns">
                <p>SNS 공유 페이스북 트위터 인스타그램 유튜브</p>
              </section>
              <section class="login">
                <p>로그인 회원가입 이용문의</p>
              </section>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"counsel.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://counsel.deu.ac.kr/counsel/index.do",
                    "final_url": "https://counsel.deu.ac.kr/counsel/index.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("counsel", "https://counsel.deu.ac.kr/counsel/index.do")

        self.assertEqual(doc["metadata"]["static_extraction_policy"], "main_page")
        self.assertIn("건강한 대학생활 적응과 성장을 위한 행복발전소", doc["raw_text"])
        self.assertIn("개인상담과 심리검사", doc["raw_text"])
        self.assertNotIn("게시물 좌측으로 이동", doc["raw_text"])
        self.assertNotIn("게시물 우측으로 이동", doc["raw_text"])
        self.assertNotIn("이전 정지 시작 다음", doc["raw_text"])
        self.assertNotIn("최신 공지 preview", doc["raw_text"])
        self.assertNotIn("PROGRAM", doc["raw_text"])
        self.assertNotIn("행사사진", doc["raw_text"])
        self.assertNotIn("SNS", doc["raw_text"])
        self.assertNotIn("로그인", doc["raw_text"])
        self.assertNotIn("회원가입", doc["raw_text"])
        self.assertIn("raw_text_length_before", doc["metadata"]["quality_filter"])
        self.assertIn("raw_text_length_after", doc["metadata"]["quality_filter"])

    def test_static_non_main_page_keeps_literal_angle_bracket_text(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <h2>참여 후기</h2>
              <p>상담을 통해 &lt;학교&gt;와 &lt;사회&gt; 사이에서 진로를 고민했습니다.</p>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/deu-support-info.do",
                    "final_url": "https://www.deu.ac.kr/www/deu-support-info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("support", "https://www.deu.ac.kr/www/deu-support-info.do")

        self.assertEqual(doc["metadata"]["static_extraction_policy"], "static_page")
        self.assertIn("<학교>", doc["raw_text"])
        self.assertIn("<사회>", doc["raw_text"])

    def test_static_page_extractor_keeps_verify_true_for_has_ssl_errors(self) -> None:
        extractor = StaticPageExtractor(allowed_hosts={"has.deu.ac.kr"})
        extractor.session.get = Mock(side_effect=requests.exceptions.SSLError("certificate expired"))

        with self.assertRaises(requests.exceptions.SSLError) as ctx:
            extractor.fetch_result("https://has.deu.ac.kr/")

        self.assertIn("keeping verify=True", str(ctx.exception))
        extractor.session.get.assert_called_once_with("https://has.deu.ac.kr/", timeout=extractor.timeout)

    def test_static_page_extractor_preserves_administration_card_sections(self) -> None:
        html = """
        <html>
          <body>
            <div id="content">
              <div class="con-box" id="adm01">
                <h4 class="h4-tit"><span>교무처</span></h4>
                <div class="item-img-list">
                  <div class="img-list">
                    <div class="txt">
                      <div class="section">
                        <div class="subject">교육혁신원</div>
                        <div class="con"><p>교육혁신 업무를 담당한다.</p></div>
                      </div>
                      <div class="section">
                        <ul class="item-sdot">
                          <li><strong>위치</strong>: 산학협력관 315호</li>
                          <li><strong>전화번호</strong>: 051-890-4373</li>
                        </ul>
                        <div class="btn-wrap">
                          <a class="btn-base">구성원 보기</a>
                          <a class="btn-base btn-w" href="https://inno.deu.ac.kr/">바로가기</a>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/deu-administration-office.do",
                    "final_url": "https://www.deu.ac.kr/www/deu-administration-office.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("institution", "https://www.deu.ac.kr/www/deu-administration-office.do")

        self.assertEqual(doc["structured_sections"][0]["section_title"], "교무처 > 교육혁신원")
        self.assertIn("상위조직: 교무처", doc["structured_sections"][0]["text"])
        self.assertIn("기관: 교육혁신원", doc["structured_sections"][0]["text"])
        self.assertIn("전화번호: 051-890-4373", doc["structured_sections"][0]["text"])
        self.assertEqual(doc["metadata"]["structure"]["types"], ["administration_office"])

    def test_static_page_extractor_preserves_organization_paths(self) -> None:
        html = """
        <html>
          <body>
            <div id="content">
              <div class="organization-wrap">
                <ol>
                  <li>
                    <div class="txt-one"><span>총장</span></div>
                    <ul>
                      <li>
                        <span class="txt-sub">국책사업본부</span>
                        <ul>
                          <li><span class="txt-sub">RISE사업단</span>
                            <ul><li><span class="txt-sub">RISE지원팀</span></li></ul>
                          </li>
                        </ul>
                      </li>
                    </ul>
                  </li>
                </ol>
              </div>
            </div>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/deu-organization.do",
                    "final_url": "https://www.deu.ac.kr/www/deu-organization.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("institution", "https://www.deu.ac.kr/www/deu-organization.do")

        self.assertEqual(doc["structured_sections"][0]["section_title"], "조직도 계층")
        self.assertIn("총장 > 국책사업본부 > RISE사업단 > RISE지원팀", doc["structured_sections"][0]["text"])
        self.assertEqual(doc["metadata"]["structure"]["types"], ["organization_chart"])

    def test_static_page_extractor_builds_generic_dom_sections(self) -> None:
        html = """
        <html>
          <body>
            <main>
              <h2>장학 안내</h2>
              <p>장학금은 성적, 소득, 봉사 기준에 따라 운영됩니다.</p>
              <ul>
                <li>신청 기간: 2026.03.01 ~ 2026.03.15</li>
                <li>문의: 장학지원팀 051-890-1051</li>
              </ul>
              <h3>제출 서류</h3>
              <table>
                <tr><th>구분</th><th>서류</th></tr>
                <tr><td>공통</td><td>신청서</td></tr>
              </table>
            </main>
          </body>
        </html>
        """
        extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
        extractor.fetch_result = Mock(
            return_value=type(
                "Result",
                (),
                {
                    "url": "https://www.deu.ac.kr/www/scholarship-info.do",
                    "final_url": "https://www.deu.ac.kr/www/scholarship-info.do",
                    "status_code": 200,
                    "headers": {},
                    "raw_html": html,
                },
            )()
        )

        doc = extractor.extract_static_page("scholarship", "https://www.deu.ac.kr/www/scholarship-info.do")

        self.assertEqual(doc["metadata"]["structure"]["types"], ["generic_dom"])
        self.assertEqual(doc["structured_sections"][0]["section_title"], "장학 안내")
        self.assertIn("- 신청 기간: 2026.03.01 ~ 2026.03.15", doc["structured_sections"][0]["text"])
        self.assertEqual(doc["structured_sections"][1]["section_title"], "제출 서류")
        self.assertIn("구분 | 서류", doc["structured_sections"][1]["text"])


    def test_static_noise_filter_removes_common_shell_for_target_sources(self) -> None:
        fixtures = {
            "fund": "장학금 신청 기간은 2026년 3월 1일부터 3월 15일까지입니다. 제출 서류를 확인하세요.",
            "lifelong": "평생교육원 강좌 접수는 온라인으로 진행되며 수강료 납부 후 등록이 완료됩니다.",
            "dormitory": "생활관 입사 신청자는 선발 결과 발표 후 지정 기간 안에 납부해야 합니다.",
            "advising": "학생상담센터 개인상담은 사전 예약 후 이용할 수 있으며 비밀보장을 원칙으로 합니다.",
            "admission": "입학 전형 일정과 제출 서류는 모집요강 기준으로 반드시 확인해야 합니다.",
        }

        for source_type, body in fixtures.items():
            with self.subTest(source_type=source_type):
                html = f"""
                <html>
                  <body>
                    <header>HOME 메뉴 로그인</header>
                    <nav>HOME</nav>
                    <main>
                      <div class="breadcrumb">HOME &gt; 게시판 목록</div>
                      <div class="share-area">공유 페이스북 트위터 카카오톡 공유 URL 복사 프린트</div>
                      <form action="/search"><label>게시물 검색</label></form>
                      <table class="board-list">
                        <tr><th>번호</th><th>제목</th><th>작성자</th><th>작성일</th><th>조회수</th></tr>
                      </table>
                      <article class="content">
                        <h2>학사 안내</h2>
                        <p>{body}</p>
                      </article>
                      <aside class="sns">SNS 영역</aside>
                      <footer>footer quick menu</footer>
                    </main>
                  </body>
                </html>
                """
                extractor = StaticPageExtractor(allowed_hosts={"www.deu.ac.kr"})
                extractor.fetch_result = Mock(
                    return_value=type(
                        "Result",
                        (),
                        {
                            "url": f"https://www.deu.ac.kr/{source_type}/info.do",
                            "final_url": f"https://www.deu.ac.kr/{source_type}/info.do",
                            "status_code": 200,
                            "headers": {},
                            "raw_html": html,
                        },
                    )()
                )

                doc = extractor.extract_static_page(source_type, f"https://www.deu.ac.kr/{source_type}/info.do")
                combined = "\n".join(
                    [doc["raw_text"], doc["table_text"]]
                    + [section["text"] for section in doc["structured_sections"]]
                )

                for noise in ("HOME", "SNS", "공유", "로그인", "번호 | 제목 | 작성자 | 작성일 | 조회수"):
                    self.assertNotIn(noise, combined)
                self.assertIn(body, combined)


if __name__ == "__main__":
    unittest.main()
