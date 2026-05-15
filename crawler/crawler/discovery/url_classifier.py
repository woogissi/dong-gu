# crawler/discovery/url_classifier.py

from urllib.parse import parse_qs, unquote, urlparse    # parse_qs : 큐 문자열을 딕셔너리 형식으로 변환

from crawler.config.domains import DOWNLOAD_EXTENSIONS


class URLClassifier:
    def get_extension(self, url: str) -> str:   # url에서 파일 확장자만 추출
        path = urlparse(url).path.lower()
        if "." in path:
            return "." + path.split(".")[-1]    #확장자가 있으면 확장자만 추출 ex) .pdf
        return ""

    def get_query_file_extension(self, query: dict[str, list[str]]) -> str:
        for key in ("ofn", "sfn", "filename", "fileName", "name"):
            for value in query.get(key, []):
                filename = unquote(value).lower()
                for ext in DOWNLOAD_EXTENSIONS:
                    if filename.endswith(ext):
                        return ext
        return ""

    def classify(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        path = parsed.path.lower()
        ext = self.get_extension(url)
        query_ext = self.get_query_file_extension(query)

        if ext in DOWNLOAD_EXTENSIONS or query_ext in DOWNLOAD_EXTENSIONS:
            return "attachment"

        if "download" in path:
            return "attachment"

        if query.get("mode", [""])[0] == "download":
            return "attachment"

        if "articleNo" in query and query.get("mode", [""])[0] == "view":
            return "board_detail"

        if query.get("mode", [""])[0] == "list":
            return "board_list"

        if "article.offset" in query:
            return "board_list"

        if path.endswith(".do"):
            return "static_page"

        return "static_page"

    def infer_source_type(self, url: str) -> str:
        lower = url.lower()

        if "deu-notice.do" in lower:
            return "notice"
        if "gra-notice.do" in lower:
            return "academic_notice"
        if "ipsi" in lower:
            return "admission"
        if "dorm" in lower:
            return "dormitory"
        if "lib" in lower:
            return "library"
        if "faq" in lower:
            return "faq"

        return "webpage"
