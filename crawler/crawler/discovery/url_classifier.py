# crawler/discovery/url_classifier.py

from urllib.parse import urlparse, parse_qs     # parse_qs : 큐 문자열을 딕셔너리 형식으로 변환

from crawler.config.domains import DOWNLOAD_EXTENSIONS


class URLClassifier:
    def get_extension(self, url: str) -> str:   # url에서 파일 확장자만 추출
        path = urlparse(url).path.lower()
        if "." in path:
            return "." + path.split(".")[-1]    #확장자가 있으면 확장자만 추출 ex) .pdf
        return ""                               #확장자가 없으면 ""반환

    def classify(self, url: str) -> str:        # page_kind 결정
        parsed = urlparse(url)
        query = parse_qs(parsed.query)          #ex) ?mode=list&article.offset=10 → {"mode": ["list"], "article.offset": ["10"]}
        path = parsed.path.lower()
        ext = self.get_extension(url)

        if ext in DOWNLOAD_EXTENSIONS:          #확장자가 있는데 download_extensions에 있으면 attachment로 반환
            return "attachment"

        if query.get("mode", [""])[0] == "download":    # mode=download 일 경우 attachment로 반환
            return "attachment"

        if "articleNo" in query and query.get("mode", [""])[0] == "view":   # articleNo=123&mode=view 일 경우 게시글 상세 페이지
            return "board_detail"

        if query.get("mode", [""])[0] == "list":    # mode=list 일 경우 게시글 목록
            return "board_list"

        if "article.offset" in query:           # ex) article.offset=10 일때는 게시글 목록(해당 주소는 페이지 넘기는 파라미터)
            return "board_list"

        if path.endswith(".do"):                # .do 로 끝나면 일반(정적)페이지
            return "static_page"

        return "static_page"                    # 다 해당 안되면 그냥 정적 페이지

    def infer_source_type(self, url: str) -> str:   # source_type 결정
        lower = url.lower()

        if "deu-notice.do" in lower:        # url에 deu-notice.do 가 포함되어있으면 일반공지(notice)
            return "notice"                 
        if "gra-notice.do" in lower:        # url에 gra-notice.do 가 포함되어있으면 학사공지(academic_notice)
            return "academic_notice"
        if "ipsi" in lower:                 # url에 ipsi 가 포함되어있으면 입학처(admission)
            return "admission"
        if "dorm" in lower:                 # url에 dorm 가 포함되어있으면 기숙사(dormitory)
            return "dormitory"
        if "lib" in lower:                  # url에 lib 가 포함되어있으면 도서관(library)
            return "library"
        if "faq" in lower:                  # url에 faq 가 포함되어있으면 FAQ(faq)
            return "faq"

        return "webpage"                    # 해당 안되면 그냥 일반 페이지