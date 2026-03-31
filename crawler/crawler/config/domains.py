# crawler/config/domains.py

ALLOWED_HOSTS = {           # 정적 탐색에서 광고등등을 막기 위함.(여기 주소가 달려있는곳만 탐색하세요~)
    "www.deu.ac.kr",
    "ipsi.deu.ac.kr",
    "dorm.deu.ac.kr",
    "lib.deu.ac.kr",
}

DOWNLOAD_EXTENSIONS = {     # 정적 크롤링 탐색에서 첨부파일 다운을 막기위한 예외 주소
    ".pdf",
    ".hwp",
    ".hwpx",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".jpg",
    ".jpeg",
    ".png",
    ".p12",
}