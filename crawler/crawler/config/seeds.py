# crawler/config/seeds.py

SEED_URLS = [       # 해당 크롤러는 밑의 주소의 정보를 크롤링함
    {
        "name": "deu_home",
        "url": "https://www.deu.ac.kr/www/index.do",
        "source_type": "homepage",
        "page_kind": "static_page",
    },
    {
        "name": "deu_notice_list",
        "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
        "source_type": "notice",
        "page_kind": "board_list",
    },
    {
        "name": "deu_gra_notice_list",
        "url": "https://www.deu.ac.kr/www/gra-notice.do?mode=list",
        "source_type": "academic_notice",
        "page_kind": "board_list",
    },
    {
        "name": "deu_ipsi_home",
        "url": "https://ipsi.deu.ac.kr/",
        "source_type": "admission",
        "page_kind": "static_page",
    },
    {
        "name": "deu_dorm_home",
        "url": "https://dorm.deu.ac.kr/",
        "source_type": "dormitory",
        "page_kind": "static_page",
    },
    {
        "name": "deu_library_home",
        "url": "https://lib.deu.ac.kr/",
        "source_type": "library",
        "page_kind": "static_page",
    },
]