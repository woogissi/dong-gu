# crawler/discovery/url_classifier.py

from urllib.parse import parse_qs, unquote, urlparse

from crawler.config.domains import DEPARTMENT_HOSTS, DOWNLOAD_EXTENSIONS


class URLClassifier:
    def get_extension(self, url: str) -> str:
        path = urlparse(url).path.lower()
        if "." in path:
            return "." + path.split(".")[-1]
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
        host = urlparse(url).netloc.lower()

        if "deu-notice.do" in lower:
            return "notice"
        if "deu-scholarship.do" in lower:
            return "scholarship"
        if "gra-notice.do" in lower:
            return "academic_notice"
        if "deu-education.do" in lower:
            return "education"
        if "deu-job.do" in lower:
            return "job"
        if "deu-support-notice.do" in lower:
            return "disability_support"
        if "deu-bids.do" in lower:
            return "bids"
        if "deu-today.do" in lower:
            return "news"
        if "deu-foundation-notices.do" in lower:
            return "foundation_notice"
        if "deu-council-notice.do" in lower:
            return "council_notice"
        if "ipsi" in lower:
            return "admission"
        if "dorm" in lower:
            return "dormitory"
        if "lib" in lower:
            return "library"
        if "faq" in lower:
            return "faq"
        if host in DEPARTMENT_HOSTS:
            return "department"

        return "webpage"
