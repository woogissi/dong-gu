# crawler/config/seeds.py

DEFAULT_SEED_POLICY = {
    "crawl_enabled": True,
    "priority": "P1",
    "source_group": None,
    "discover_board_candidates": False,
}


def normalize_seed(seed: dict) -> dict:
    normalized = {**DEFAULT_SEED_POLICY, **seed}
    normalized["source_group"] = normalized.get("source_group") or normalized.get("source_type")

    if "discover_board_candidates" not in seed:
        normalized["discover_board_candidates"] = normalized.get("page_kind") in {"seed", "static_page"}

    return normalized


def iter_enabled_seeds(page_kind: str | None = None) -> list[dict]:
    seeds = [normalize_seed(seed) for seed in SEED_URLS]
    if page_kind is not None:
        seeds = [seed for seed in seeds if seed.get("page_kind") == page_kind]
    return [seed for seed in seeds if seed.get("crawl_enabled", True)]

SEED_URLS = [       # 해당 크롤러는 밑의 주소의 정보를 크롤링함
    {
        "name": "deu_home",
        "url": "https://www.deu.ac.kr/www/index.do",
        "source_type": "homepage",
        "page_kind": "static_page",
        "priority": "P0",
    },
    {
        "name": "deu_notice_list",
        "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
        "source_type": "notice",
        "page_kind": "board_list",
        "priority": "P0",
    },
    {
        "name": "deu_gra_notice_list",
        "url": "https://www.deu.ac.kr/www/gra-notice.do?mode=list",
        "source_type": "academic_notice",
        "page_kind": "board_list",
        "priority": "P0",
    },
    {
        "name": "deu_ipsi_home",
        "url": "https://ipsi.deu.ac.kr/main.do",
        "source_type": "admission",
        "page_kind": "static_page",
        "priority": "P0",
    },
    {
        "name": "deu_ipsi_susi_guide",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=1",
        "source_type": "admission",
        "page_kind": "static_page",
    },
    {
        "name": "deu_ipsi_jungsi_guide",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=2",
        "source_type": "admission",
        "page_kind": "static_page",
    },
    {
        "name": "deu_ipsi_transfer_archive",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=PfBqkhQSW5ucDw9DG8WhnQ%3D%3D",
        "source_type": "admission",
        "page_kind": "static_page",
    },
    {
        "name": "deu_academic_support_home",
        "url": "https://dess.deu.ac.kr/",
        "source_type": "academic_support",
        "page_kind": "static_page",
    },
    {
        "name": "deu_dorm_home",
        "url": "https://dorm.deu.ac.kr/",
        "source_type": "dormitory",
        "page_kind": "static_page",
    },
    {
        "name": "deu_dorm_hyomin_intro",
        "url": "https://dorm.deu.ac.kr/10/1010.do",
        "source_type": "dormitory",
        "page_kind": "static_page",
    },
    {
        "name": "deu_dorm_hyomin_admission",
        "url": "https://dorm.deu.ac.kr/30/3010.do",
        "source_type": "dormitory",
        "page_kind": "static_page",
    },
    {
        "name": "deu_happy_dorm_intro",
        "url": "https://dorm.deu.ac.kr/10/1020.do",
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
        "name": "deu_shuttle_bus",
        "url": "https://www.deu.ac.kr/www/deu-bus.do",
        "source_type": "campus",
        "page_kind": "static_page",
    },
    {
        "name": "deu_dining_hall",
        "url": "https://www.deu.ac.kr/www/deu-dining-hall.do",
        "source_type": "welfare",
        "page_kind": "static_page",
    },
    {
        "name": "deu_cloud_email",
        "url": "https://www.deu.ac.kr/www/deu-cloud.do",
        "source_type": "it_service",
        "page_kind": "static_page",
    },
    {
        "name": "deu_heyyoung",
        "url": "https://www.deu.ac.kr/www/deu-heyyoung.do",
        "source_type": "it_service",
        "page_kind": "static_page",
    },
    {
        "name": "deu_facility_info",
        "url": "https://www.deu.ac.kr/www/deu-facility-info.do",
        "source_type": "facility",
        "page_kind": "static_page",
    },
    {
        "name": "deu_disability_support_info",
        "url": "https://www.deu.ac.kr/www/deu-support-info.do",
        "source_type": "disability_support",
        "page_kind": "static_page",
    },
    {
        "name": "deu_phone",
        "url": "https://www.deu.ac.kr/www/phone.do",
        "source_type": "institution",
        "page_kind": "static_page",
    },
    {
        "name": "deu_rules",
        "url": "https://www.deu.ac.kr/www/rules.do",
        "source_type": "institution",
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
