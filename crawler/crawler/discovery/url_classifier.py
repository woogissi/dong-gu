# crawler/discovery/url_classifier.py

from urllib.parse import urlparse, parse_qs

from crawler.config.domains import DOWNLOAD_EXTENSIONS


class URLClassifier:
    def get_extension(self, url: str) -> str:
        path = urlparse(url).path.lower()
        if "." in path:
            return "." + path.split(".")[-1]
        return ""

    def classify(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        path = parsed.path.lower()
        ext = self.get_extension(url)

        if ext in DOWNLOAD_EXTENSIONS:
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