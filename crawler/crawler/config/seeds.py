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
    {
        "name": "deu_ipp_home",
        "url": "https://ipp.deu.ac.kr/",
        "source_type": "ipp",
        "page_kind": "static_page",
    },
    {
        "name": "deu_pluscenter_home",
        "url": "https://deu.ac.kr/pluscenter/index.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
    },
    {
        "name": "deu_career_home",
        "url": "https://career.deu.ac.kr/career/Page/Default.aspx",
        "source_type": "career",
        "page_kind": "static_page",
    },
    {
        "name": "deu_lifelong_home",
        "url": "https://lifelong.deu.ac.kr/",
        "source_type": "lifelong",
        "page_kind": "static_page",
    },
    {
        "name": "deu_ctl_home",
        "url": "https://ctl.deu.ac.kr/ctl/index.do",
        "source_type": "ctl",
        "page_kind": "static_page",
    },
    {
        "name": "deu_collabo_home",
        "url": "https://collabo.deu.ac.kr/collabo/index.do",
        "source_type": "collabo",
        "page_kind": "static_page",
    },
    {
        "name": "deu_has_home",
        "url": "https://has.deu.ac.kr/",
        "source_type": "has",
        "page_kind": "static_page",
    },
    {
        "name": "deu_bhcoss_home",
        "url": "https://bhcoss.deu.ac.kr/bhcoss/index.do",
        "source_type": "bhcoss",
        "page_kind": "static_page",
    },
    {
        "name": "deu_lang_intro_home",
        "url": "https://deuhome.deu.ac.kr/lang_intro/index.do",
        "source_type": "language_intro",
        "page_kind": "static_page",
    },
    {
        "name": "deu_language_home",
        "url": "https://deuhome.deu.ac.kr/language/index.do",
        "source_type": "language",
        "page_kind": "static_page",
    },
    {
        "name": "deu_counsel_home",
        "url": "https://counsel.deu.ac.kr/counsel/index.do",
        "source_type": "counsel",
        "page_kind": "static_page",
    },
    {
        "name": "deu_advising_home",
        "url": "https://advising.deu.ac.kr/advising/index.do",
        "source_type": "advising",
        "page_kind": "static_page",
    },
    {
        "name": "deu_webzine_home",
        "url": "https://webzine.deu.ac.kr/webzine",
        "source_type": "webzine",
        "page_kind": "static_page",
    },
    {
        "name": "deu_fund_home",
        "url": "https://deufund.deu.ac.kr/exchange/main.do",
        "source_type": "fund",
        "page_kind": "static_page",
    },

]