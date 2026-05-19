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


def iter_seed_catalog(page_kind: str | None = None) -> list[dict]:
    seeds = [normalize_seed(seed) for seed in SEED_URLS]
    if page_kind is not None:
        seeds = [seed for seed in seeds if seed.get("page_kind") == page_kind]
    return seeds


def iter_enabled_seeds(page_kind: str | None = None) -> list[dict]:
    return [seed for seed in iter_seed_catalog(page_kind) if seed.get("crawl_enabled", True)]

SEED_URLS = [       # 해당 크롤러는 밑의 주소의 정보를 크롤링함
    {
        "name": "deu_home",
        "url": "https://www.deu.ac.kr/www/index.do",
        "source_type": "homepage",
        "page_kind": "static_page",
        "priority": "P0",
    },
    {
        "name": "deu_president_message",
        "url": "https://www.deu.ac.kr/www/deu-message.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_student_council",
        "url": "https://www.deu.ac.kr/www/deu-student-council.do",
        "source_type": "student_life",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_former_presidents",
        "url": "https://www.deu.ac.kr/www/former-university-presidents.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_campus_map",
        "url": "https://www.deu.ac.kr/www/deu-campus-map.do",
        "source_type": "campus",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_campus_gaya",
        "url": "https://www.deu.ac.kr/www/deu-campus-gaya.do",
        "source_type": "campus",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_university_philosophy",
        "url": "https://www.deu.ac.kr/www/university-philosophy.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_vision",
        "url": "https://www.deu.ac.kr/www/deu-vision.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_corporation",
        "url": "https://www.deu.ac.kr/www/deu-corporation.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_foundation_notices_list",
        "url": "https://www.deu.ac.kr/www/deu-foundation-notices.do?mode=list",
        "source_type": "foundation_notice",
        "page_kind": "board_list",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_foundation_mom",
        "url": "https://www.deu.ac.kr/www/deu-foundation-mom.do",
        "source_type": "foundation",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_safety",
        "url": "https://www.deu.ac.kr/www/deu-safety.do",
        "source_type": "safety",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_overview",
        "url": "https://www.deu.ac.kr/www/deu-overview.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_history_2020",
        "url": "https://www.deu.ac.kr/www/deu-history-2020.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P3",
        "crawl_enabled": True,
    },
    {
        "name": "deu_council_notice_list",
        "url": "https://www.deu.ac.kr/www/deu-council-notice.do?mode=list",
        "source_type": "council_notice",
        "page_kind": "board_list",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ui",
        "url": "https://www.deu.ac.kr/www/deu-ui.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P3",
        "crawl_enabled": True,
    },
    {
        "name": "deu_song",
        "url": "https://www.deu.ac.kr/www/deu-song.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P3",
        "crawl_enabled": True,
    },
    {
        "name": "deu_character",
        "url": "https://www.deu.ac.kr/www/deu-character.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P3",
        "crawl_enabled": True,
    },
    {
        "name": "deu_affiliated_institution",
        "url": "https://www.deu.ac.kr/www/deu-affiliated-Institution.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_college",
        "url": "https://www.deu.ac.kr/www/deu-college.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_graduate_school",
        "url": "https://www.deu.ac.kr/www/deu-graduate-school.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_rule",
        "url": "https://www.deu.ac.kr/www/deu-rule.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_curriculum",
        "url": "https://www.deu.ac.kr/www/deu-curriculum.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_explanation",
        "url": "https://www.deu.ac.kr/www/deu-explanation.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_microdegree",
        "url": "https://www.deu.ac.kr/www/deu-microdegree.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_consortium",
        "url": "https://www.deu.ac.kr/www/deu-consortium.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_rnd",
        "url": "https://www.deu.ac.kr/www/deu-rnd.do",
        "source_type": "research",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_notice_list",
        "url": "https://www.deu.ac.kr/www/deu-notice.do?mode=list",
        "source_type": "notice",
        "page_kind": "board_list",
        "priority": "P0",
        "crawl_enabled": True,
    },
    {
        "name": "deu_scholarship_list",
        "url": "https://www.deu.ac.kr/www/deu-scholarship.do?mode=list",
        "source_type": "scholarship",
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
        "name": "deu_education_list",
        "url": "https://www.deu.ac.kr/www/deu-education.do?mode=list",
        "source_type": "education",
        "page_kind": "board_list",
        "priority": "P1",
    },
    {
        "name": "deu_job_list",
        "url": "https://www.deu.ac.kr/www/deu-job.do?mode=list",
        "source_type": "job",
        "page_kind": "board_list",
        "priority": "P1",
    },
    {
        "name": "deu_support_notice_list",
        "url": "https://www.deu.ac.kr/www/deu-support-notice.do?mode=list",
        "source_type": "disability_support",
        "page_kind": "board_list",
        "priority": "P1",
    },
    {
        "name": "deu_bids_list",
        "url": "https://www.deu.ac.kr/www/deu-bids.do?mode=list",
        "source_type": "bids",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_today_list",
        "url": "https://www.deu.ac.kr/www/deu-today.do?mode=list",
        "source_type": "news",
        "page_kind": "board_list",
        "priority": "P2",
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
        "name": "deu_ipsi_submenu_d0lb4mk2",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=D0Lb4Mk2mKJBZuJJDzIzEw%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_submenu_ye0oe4wa",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=Ye0Oe4WAUjlEoUsext6iJw%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_menuord_3",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=3",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_submenu_cpat8s71",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=Cpat8s71FjlAdfevJKfIDw%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_transfer_archive",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=PfBqkhQSW5ucDw9DG8WhnQ%3D%3D",
        "source_type": "admission",
        "page_kind": "static_page",
    },
    {
        "name": "deu_ipsi_submenu_cf5pbokb",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=Cf5PbokbyGk5VfLO98MtrA%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_submenu_plus3jey",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=%2B3JEYt36zn8xvrwKcNVv3w%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_menuord_5",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=5",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_submenu_khw0im8v",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=KHw0IM8v%2BcgQ4zs30Ih%2B4w%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_menuord_6",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=6",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_submenu_dlhayfis",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuUrl=dLhAYFiSDJmIo3FeS8m3ug%3D%3D",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_university_detail",
        "url": "https://ipsi.deu.ac.kr/universityDetail.do",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
    {
        "name": "deu_ipsi_menuord_7",
        "url": "https://ipsi.deu.ac.kr/submenu.do?menuord=7",
        "source_type": "admission",
        "source_group": "admission",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
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
    {
        "name": "deu_research_ethics_home",
        "url": "https://reethics.deu.ac.kr/resch/index.do",
        "source_type": "research_ethics",
        "page_kind": "static_page",
        "priority": "P2",
        "crawl_enabled": True,
    },
]

# Additional seed URLs tracked in docs/seed.md.
SEED_URLS.extend([
    {
        "name": "deu_dormitory_list",
        "url": "https://www.deu.ac.kr/www/deu-dormitory.do?mode=list",
        "source_type": "dormitory",
        "page_kind": "board_list",
        "priority": "P1",
    },
    {
        "name": "deu_external_list",
        "url": "https://www.deu.ac.kr/www/deu-external.do?mode=list",
        "source_type": "external_notice",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_lostfound_list",
        "url": "https://www.deu.ac.kr/www/deu-lostfound.do?mode=list",
        "source_type": "lostfound",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_reference_list",
        "url": "https://www.deu.ac.kr/www/deu-reference.do?mode=list",
        "source_type": "reference",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_news_list",
        "url": "https://www.deu.ac.kr/www/deu-news.do?mode=list",
        "source_type": "news",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_newsletter_list",
        "url": "https://www.deu.ac.kr/www/deu-newsletter.do?mode=list",
        "source_type": "newsletter",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_collabo",
        "url": "https://www.deu.ac.kr/www/deu-collabo.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_specialization",
        "url": "https://www.deu.ac.kr/www/deu-specialization.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_campus_yangjeong",
        "url": "https://www.deu.ac.kr/www/deu-campus-yangjeong.do",
        "source_type": "campus",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_campus_map_image",
        "url": "https://www.deu.ac.kr/_res/deu/www/img/sub/campus-map.jpg",
        "source_type": "campus",
        "page_kind": "static_page",
        "priority": "P3",
    },
    {
        "name": "deu_organization",
        "url": "https://www.deu.ac.kr/www/deu-organization.do",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_teacher_home",
        "url": "https://deuhome.deu.ac.kr/teacher/index.do",
        "source_type": "teacher",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_administration_office",
        "url": "https://www.deu.ac.kr/www/deu-administration-office.do#adm01",
        "source_type": "institution",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_innovation_home",
        "url": "https://inno.deu.ac.kr/inno/index.do",
        "source_type": "innovation",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_support_org",
        "url": "https://www.deu.ac.kr/www/deu-support-org.do",
        "source_type": "disability_support",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_support_edu",
        "url": "https://www.deu.ac.kr/www/deu-support-edu.do",
        "source_type": "disability_support",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_culture_innovation_home",
        "url": "https://vsc.deu.ac.kr/culture/index.do",
        "source_type": "culture_innovation",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_deuhome",
        "url": "https://deuhome.deu.ac.kr/pluscenter/index.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ipp_page_111",
        "url": "https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=111",
        "source_type": "ipp",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ipp_page_113",
        "url": "https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=113",
        "source_type": "ipp",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ipp_page_114",
        "url": "https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=114",
        "source_type": "ipp",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ipp_page_115",
        "url": "https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=115",
        "source_type": "ipp",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_intro",
        "url": "https://deu.ac.kr/pluscenter/sub01_01.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_program",
        "url": "https://deu.ac.kr/pluscenter/sub01_05.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_location",
        "url": "https://deu.ac.kr/pluscenter/sub01_06.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_consulting",
        "url": "https://deu.ac.kr/pluscenter/sub03_04.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_pluscenter_notice",
        "url": "https://deu.ac.kr/pluscenter/sub04_07.do",
        "source_type": "pluscenter",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ctl_intro",
        "url": "https://ctl.deu.ac.kr/ctl/sub01_01.do",
        "source_type": "ctl",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ctl_teaching",
        "url": "https://ctl.deu.ac.kr/ctl/sub02_01.do",
        "source_type": "ctl",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ctl_learning",
        "url": "https://ctl.deu.ac.kr/ctl/sub03_01.do",
        "source_type": "ctl",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_ctl_guide",
        "url": "https://ctl.deu.ac.kr/ctl/sub05_03.do",
        "source_type": "ctl",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_exchange_home",
        "url": "https://deuhome.deu.ac.kr/exchange/index.do",
        "source_type": "exchange",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_exchange_intro",
        "url": "https://deuhome.deu.ac.kr/exchange/sub01_01.do",
        "source_type": "exchange",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_exchange_program",
        "url": "https://deuhome.deu.ac.kr/exchange/sub03_03.do",
        "source_type": "exchange",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_exchange_notice",
        "url": "https://deuhome.deu.ac.kr/exchange/sub05_01.do",
        "source_type": "exchange",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_library_history",
        "url": "https://lib.deu.ac.kr/intro_history.mir",
        "source_type": "library",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_library_rule",
        "url": "https://lib.deu.ac.kr/intro_rule.mir",
        "source_type": "library",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_library_notice_list",
        "url": "https://lib.deu.ac.kr/sb/default_notice_list.mir",
        "source_type": "library",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_library_faq_list",
        "url": "https://lib.deu.ac.kr/sb/faq_faq_list.mir#link",
        "source_type": "library",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_dorm_main",
        "url": "https://dorm.deu.ac.kr/00/0000.do",
        "source_type": "dormitory",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_dorm_notice",
        "url": "https://dorm.deu.ac.kr/20/2010.do",
        "source_type": "dormitory",
        "page_kind": "board_list",
        "priority": "P2",
    },
    {
        "name": "deu_dorm_life",
        "url": "https://dorm.deu.ac.kr/40/4010.do",
        "source_type": "dormitory",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_dorm_faq",
        "url": "https://dorm.deu.ac.kr/60/6010.do#",
        "source_type": "dormitory",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_enter_graduate_school",
        "url": "https://www.deu.ac.kr/www/deu-enter-graduateschool.do",
        "source_type": "admission",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_schedule_list",
        "url": "https://www.deu.ac.kr/www/scheduleList.do",
        "source_type": "academic_calendar",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_academic_leave",
        "url": "https://dess.deu.ac.kr/?mid=Page1",
        "source_type": "academic_support",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_academic_return",
        "url": "https://dess.deu.ac.kr/?mid=Page3",
        "source_type": "academic_support",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_club",
        "url": "https://www.deu.ac.kr/www/deu-club.do",
        "source_type": "student_life",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_sbus",
        "url": "https://www.deu.ac.kr/www/deu-sbus.do",
        "source_type": "campus",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_wifi",
        "url": "https://www.deu.ac.kr/www/deu-wifi.do",
        "source_type": "it_service",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_college_engineering",
        "url": "https://www.deu.ac.kr/www/deu-college-of-engineering.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_college_software",
        "url": "https://www.deu.ac.kr/www/deu-college-of-software.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_college_healthcare",
        "url": "https://www.deu.ac.kr/www/deu-college-of-healthcare.do",
        "source_type": "academic",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_industry_academic",
        "url": "https://www.deu.ac.kr/www/deu-industry-academic.do",
        "source_type": "research",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_academic_class",
        "url": "https://dess.deu.ac.kr/?mid=Page11",
        "source_type": "academic_support",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_academic_graduation",
        "url": "https://dess.deu.ac.kr/?mid=Page15",
        "source_type": "academic_support",
        "page_kind": "static_page",
        "priority": "P1",
    },
    {
        "name": "deu_swcc_computer",
        "url": "https://swcc.deu.ac.kr/computer/index.do",
        "source_type": "software_college",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_swcc_software_engineering",
        "url": "https://swcc.deu.ac.kr/se/index.do",
        "source_type": "software_college",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_swcc_applied_software",
        "url": "https://swcc.deu.ac.kr/asw/index.do",
        "source_type": "software_college",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_swcc_ai",
        "url": "https://swcc.deu.ac.kr/ai/index.do",
        "source_type": "software_college",
        "page_kind": "static_page",
        "priority": "P2",
    },
    {
        "name": "deu_swcc_game",
        "url": "https://swcc.deu.ac.kr/game/index.do",
        "source_type": "software_college",
        "page_kind": "static_page",
        "priority": "P2",
    },
])

from hashlib import blake2s as _blake2s
from urllib.parse import parse_qs as _parse_qs, urlparse as _urlparse


def _doc_seed_name(url: str) -> str:
    parsed = _urlparse(url)
    host = parsed.netloc.lower().replace(".", "_").replace("-", "_")
    path = parsed.path.strip("/").replace("/", "_").replace(".", "_").replace("-", "_")
    digest = _blake2s(url.encode("utf-8"), digest_size=4).hexdigest()
    stem = "_".join(part for part in (host, path) if part)[:70].strip("_")
    return f"doc_seed_{stem}_{digest}"


def _doc_seed_source_type(url: str) -> str:
    parsed = _urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if "ipsi" in host:
        return "admission"
    if "dorm" in host:
        return "dormitory"
    if "lib" in host:
        return "library"
    if "teacher" in path:
        return "teacher"
    if "exchange" in path:
        return "exchange"
    if "pluscenter" in path:
        return "pluscenter"
    if "ctl" in host:
        return "ctl"
    if "collabo" in host or "collabo" in path:
        return "collabo"
    if "bhcoss" in host:
        return "bhcoss"
    if "advising" in host:
        return "advising"
    if "deufund" in host:
        return "fund"
    if "sanhak" in host or "industry" in path:
        return "research"
    if host == "www.deu.ac.kr":
        return "institution"
    if host.endswith(".deu.ac.kr"):
        return "department"
    return "external"


def _doc_seed_page_kind(url: str) -> str:
    parsed = _urlparse(url)
    path = parsed.path.lower()
    query = _parse_qs(parsed.query)
    if query.get("mode", [""])[0] == "list":
        return "board_list"
    if "selectnttlist" in path:
        return "board_list"
    if path.endswith("_list.mir"):
        return "board_list"
    if any(token in path for token in ("notice", "faq", "lostproperty", "libtoday")):
        return "board_list"
    return "static_page"


def _make_doc_seed(url: str) -> dict:
    return {
        "name": _doc_seed_name(url),
        "url": url,
        "source_type": _doc_seed_source_type(url),
        "page_kind": _doc_seed_page_kind(url),
        "priority": "P2",
    }


_DOC_SEED_URLS = """
https://www.deu.ac.kr/www/deu-busan-multicultural.do
https://www.deu.ac.kr/www/deu-busan-multicultural-program.do
https://deuhome.deu.ac.kr/teacher/sub01_01.do
https://deuhome.deu.ac.kr/teacher/sub01_02.do
https://deuhome.deu.ac.kr/teacher/sub01_03.do
https://deuhome.deu.ac.kr/teacher/sub01_04.do
https://deuhome.deu.ac.kr/teacher/sub01_05.do
https://deuhome.deu.ac.kr/teacher/sub02_01.do
https://deuhome.deu.ac.kr/teacher/sub02_02.do
https://deuhome.deu.ac.kr/teacher/sub02_03.do
https://deuhome.deu.ac.kr/teacher/sub02_04.do
https://deuhome.deu.ac.kr/teacher/sub02_05.do
https://deuhome.deu.ac.kr/teacher/sub02_06.do
https://deuhome.deu.ac.kr/teacher/sub02_07.do
https://deuhome.deu.ac.kr/teacher/sub02_08.do
https://deuhome.deu.ac.kr/teacher/sub02_09.do
https://deuhome.deu.ac.kr/teacher/sub02_10.do
https://deuhome.deu.ac.kr/teacher/sub03_01.do
https://deuhome.deu.ac.kr/teacher/sub03_02.do
https://deuhome.deu.ac.kr/teacher/sub03_03.do
https://deuhome.deu.ac.kr/teacher/sub03_04.do
https://deuhome.deu.ac.kr/teacher/sub04_01.do
https://deuhome.deu.ac.kr/teacher/sub04_02.do
https://deuhome.deu.ac.kr/teacher/sub04_03.do
https://deuhome.deu.ac.kr/teacher/sub04_04.do
https://deuhome.deu.ac.kr/teacher/sub04_05.do
https://deuhome.deu.ac.kr/teacher/sub04_06.do
https://deuhome.deu.ac.kr/teacher/sub04.do
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=814
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=211
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=212
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=213
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=214
https://ipp.deu.ac.kr/Contents/Contents.aspx?PageNo=215
https://deu.ac.kr/pluscenter/sub01_02.do
https://deu.ac.kr/pluscenter/sub01_04.do
https://deu.ac.kr/pluscenter/sub04_05.do
https://deu.ac.kr/pluscenter/sub04_06.do
https://deu.ac.kr/pluscenter/sub04_09.do
https://deu.ac.kr/pluscenter/sub04_10.do
https://deu.ac.kr/pluscenter/education.do
https://ctl.deu.ac.kr/ctl/sub01_03.do
https://ctl.deu.ac.kr/ctl/sub01_04.do
https://ctl.deu.ac.kr/ctl/sub01_05.do
https://ctl.deu.ac.kr/ctl/sub02_02.do
https://ctl.deu.ac.kr/ctl/sub03_02.do
https://ctl.deu.ac.kr/ctl/sub04_01.do
https://ctl.deu.ac.kr/ctl/sub04_02.do
https://ctl.deu.ac.kr/ctl/sub04_03.do
https://ctl.deu.ac.kr/ctl/sub06_01.do
https://collabo.deu.ac.kr/collabo/sub01_01.do
https://collabo.deu.ac.kr/collabo/sub01_02.do
https://collabo.deu.ac.kr/collabo/sub01_03.do
https://collabo.deu.ac.kr/collabo/sub02_01.do
https://collabo.deu.ac.kr/collabo/sub02_02.do
https://collabo.deu.ac.kr/collabo/sub03_01.do
https://collabo.deu.ac.kr/collabo/sub04_01.do
https://bhcoss.deu.ac.kr/bhcoss/sub01_01.do
https://bhcoss.deu.ac.kr/bhcoss/sub01_03.do
https://bhcoss.deu.ac.kr/bhcoss/sub01_05.do
https://bhcoss.deu.ac.kr/bhcoss/sub02_01.do
https://bhcoss.deu.ac.kr/bhcoss/sub02_02.do
https://bhcoss.deu.ac.kr/bhcoss/sub04_01.do
https://bhcoss.deu.ac.kr/bhcoss/sub04_03.do
https://bhcoss.deu.ac.kr/bhcoss/sub04_05.do
https://bhcoss.deu.ac.kr/bhcoss/sub02_02.do?mode=download&articleNo=9595&attachNo=68341
https://deuhome.deu.ac.kr/exchange/sub01_02.do
https://deuhome.deu.ac.kr/exchange/sub01_03.do
https://deuhome.deu.ac.kr/exchange/sub01_04_01.do
https://deuhome.deu.ac.kr/exchange/sub01_05.do
https://deuhome.deu.ac.kr/exchange/sub01_06.do
https://deuhome.deu.ac.kr/exchange/sub02_01.do
https://deuhome.deu.ac.kr/exchange/sub02_02.do
https://deuhome.deu.ac.kr/exchange/sub03_01.do
https://deuhome.deu.ac.kr/exchange/sub04_03.do
https://deuhome.deu.ac.kr/exchange/sub06_01_01.do
https://deuhome.deu.ac.kr/exchange/sub06_01_02.do
https://deuhome.deu.ac.kr/exchange/sub06_02_01.do
https://deuhome.deu.ac.kr/exchange/sub06_02_02.do
https://deuhome.deu.ac.kr/exchange/sub06_03_04.do
https://deuhome.deu.ac.kr/exchange/sub06_04_01.do
https://deuhome.deu.ac.kr/exchange/sub06_04_02.do
https://deuhome.deu.ac.kr/exchange/sub06_04_03.do
https://deuhome.deu.ac.kr/exchange/sub01_04_01.do?mode=download&articleNo=27010&attachNo=56444
https://deuhome.deu.ac.kr/exchange/sub01_04_02.do?mode=download&articleNo=27800&attachNo=57801
https://deuhome.deu.ac.kr/exchange/sub01_04_03.do?mode=download&articleNo=27801&attachNo=57802
https://deuhome.deu.ac.kr/exchange/sub01_04_04.do?mode=download&articleNo=27802&attachNo=57806
https://deuhome.deu.ac.kr/exchange/sub06_03_01.do?mode=download&articleNo=34710&attachNo=64631
https://deuhome.deu.ac.kr/exchange/sub06_01_03.do
https://deuhome.deu.ac.kr/exchange/sub05_03.do
https://deuhome.deu.ac.kr/language/sub01_01.do
https://deuhome.deu.ac.kr/language/sub01_02.do
https://deuhome.deu.ac.kr/language/sub01_03.do
https://deuhome.deu.ac.kr/language/sub01_05.do
https://deuhome.deu.ac.kr/language/sub03_01.do
https://deuhome.deu.ac.kr/language/sub03_02.do
https://deuhome.deu.ac.kr/language/sub03_03.do
https://deuhome.deu.ac.kr/language/sub03_04.do
https://deuhome.deu.ac.kr/language/sub08_01.do
https://deuhome.deu.ac.kr/language/sub08_02.do
https://deuhome.deu.ac.kr/language/sub04_01.do
https://advising.deu.ac.kr/advising/sub01_01.do
https://advising.deu.ac.kr/advising/sub01_02.do
https://advising.deu.ac.kr/advising/sub01_03.do
https://advising.deu.ac.kr/advising/sub01_04.do
https://advising.deu.ac.kr/advising/sub02_01.do
https://advising.deu.ac.kr/advising/sub02_02.do
https://advising.deu.ac.kr/advising/sub02_04.do
https://advising.deu.ac.kr/advising/sub03_01.do
https://advising.deu.ac.kr/advising/sub03_02.do
https://advising.deu.ac.kr/advising/sub04_01.do
https://advising.deu.ac.kr/advising/sub04_02.do
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1067&cntntsId=1028
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1068&cntntsId=1029
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1069&cntntsId=1030
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1070&cntntsId=1031
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1071&cntntsId=1032
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1072&cntntsId=1033
https://deufund.deu.ac.kr/exchange/cm/cntnts/cntntsView.do?mi=1074&cntntsId=1034
https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=2041&bbsId=2041
https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=1085&bbsId=1063
https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=1086&bbsId=1061
https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=1087&bbsId=1062
https://lib.deu.ac.kr/intro_data.mir
https://lib.deu.ac.kr/intro_staff.mir
https://lib.deu.ac.kr/intro_map.mir
https://lib.deu.ac.kr/sb/default_elecInfonotice_list.mir
https://lib.deu.ac.kr/sb/libtoday_libtoday_list.mir
https://lib.deu.ac.kr/sb/default_lostproperty_list.mir
https://www.deu.ac.kr/www/deu-museum.do
https://www.deu.ac.kr/www/deu-museum-info.do
https://www.deu.ac.kr/www/deu-museum-showcase.do
https://www.deu.ac.kr/www/deu-museum-notice.do
https://www.deu.ac.kr/www/deu-museum-collection.do
https://dorm.deu.ac.kr/10/1030.do
https://dorm.deu.ac.kr/10/1040.do
https://dorm.deu.ac.kr/10/1050.do
https://dorm.deu.ac.kr/10/1051.do
https://dorm.deu.ac.kr/10/1052.do
https://dorm.deu.ac.kr/20/2011.do
https://dorm.deu.ac.kr/20/2012.do
https://dorm.deu.ac.kr/20/2020.do
https://dorm.deu.ac.kr/20/2021.do
https://dorm.deu.ac.kr/20/2022.do
https://dorm.deu.ac.kr/20/2030.do
https://dorm.deu.ac.kr/20/2031.do
https://dorm.deu.ac.kr/30/3020.do
https://dorm.deu.ac.kr/30/3030.do
https://dorm.deu.ac.kr/40/4020.do
https://dorm.deu.ac.kr/40/4030.do
https://dorm.deu.ac.kr/40/4040.do
https://dorm.deu.ac.kr/40/4050.do
https://dorm.deu.ac.kr/40/4051.do
https://www.deu.ac.kr/www/deu-training.do
https://www.deu.ac.kr/www/deu-training-history.do
https://www.deu.ac.kr/www/deu-student-news.do
https://www.deu.ac.kr/www/deu-student-studio.do
https://www.deu.ac.kr/www/deu-studeio-model.do
https://www.deu.ac.kr/www/deu-preschool.do
https://www.deu.ac.kr/www/deu-preschool-info.do
https://www.deu.ac.kr/www/deu-preschool-notice.do
https://www.deu.ac.kr/www/deu-bls.do
https://www.deu.ac.kr/www/deu-bls-org.do
https://www.deu.ac.kr/www/deu-bls-education.do
https://www.deu.ac.kr/www/deu-bls-qa.do
https://www.deu.ac.kr/www/deu-bls-site.do
https://www.deu.ac.kr/www/deu-human-rights.do
https://www.deu.ac.kr/www/deu-clinic.do
https://ipsi.deu.ac.kr/submenu.do?menuUrl=2Yx5AdyROxyzbsACUoXUCQ%3d%3d&
https://ipsi.deu.ac.kr/submenu.do?menuUrl=DTTsrvKlAO%2b6D7zGxhueqA%3d%3d&
https://ipsi.deu.ac.kr/submenu.do?menuUrl=rbcJe3D1VGg%2bSR3ANL7Baw%3d%3d&
https://ipsi.deu.ac.kr/sub/pass/index.html
https://ipsi.deu.ac.kr/file/download.do?sfn=20251014062047048_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%88%98%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%88%98%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf
https://ipsi.deu.ac.kr/file/download.do?sfn=20251014062047235_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%88%98%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%88%98%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp
https://ipsi.deu.ac.kr/file/download.do?sfn=20251229094856660_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%95%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%95%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf
https://ipsi.deu.ac.kr/file/download.do?sfn=20251229094856738_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%95%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%95%ec%8b%9c+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp
https://ipsi.deu.ac.kr/file/download.do?sfn=20260210064902801_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%84%ea%b8%b0+%ed%8e%b8%ec%9e%85%ec%83%9d+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%84%ea%b8%b0+%ed%8e%b8%ec%9e%85%ec%83%9d+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).pdf
https://ipsi.deu.ac.kr/file/download.do?sfn=20260210064902894_2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%84%ea%b8%b0+%ed%8e%b8%ec%9e%85%ec%83%9d+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp&sfp=common%2f&ofn=2026%ed%95%99%eb%85%84%eb%8f%84+%ec%a0%84%ea%b8%b0+%ed%8e%b8%ec%9e%85%ec%83%9d+%eb%aa%a8%ec%a7%91%ec%9a%94%ea%b0%95(%eb%8f%99%ec%9d%98%eb%8c%80).hwp
https://ipsi.deu.ac.kr/file/pdfDown.pdf?sfn=20240718114925216_2025%ED%95%99%EB%85%84%EB%8F%84%20%EB%8F%99%EC%9D%98%EB%8C%80%ED%95%99%EA%B5%90%20%ED%95%99%EC%83%9D%EB%B6%80%EC%A2%85%ED%95%A9%EC%A0%84%ED%98%95%20%EA%B0%80%EC%9D%B4%EB%93%9C%EB%B6%81.pdf&sfp=common/&ofn=20240718114925216_2025%ED%95%99%EB%85%84%EB%8F%84%20%EB%8F%99%EC%9D%98%EB%8C%80%ED%95%99%EA%B5%90%20%ED%95%99%EC%83%9D%EB%B6%80%EC%A2%85%ED%95%A9%EC%A0%84%ED%98%95%20%EA%B0%80%EC%9D%B4%EB%93%9C%EB%B6%81.pdf
https://ipsi.deu.ac.kr/file/pdfDown.pdf?sfn=20260210065952301_2026%ED%95%99%EB%85%84%EB%8F%84%20%EC%A0%84%EA%B8%B0%20%ED%8E%B8%EC%9E%85%EC%83%9D%20%EB%AA%A8%EC%A7%91%EC%9A%94%EA%B0%95(%EB%8F%99%EC%9D%98%EB%8C%80).pdf&sfp=common/&ofn=20260210065952301_2026%ED%95%99%EB%85%84%EB%8F%84%20%EC%A0%84%EA%B8%B0%20%ED%8E%B8%EC%9E%85%EC%83%9D%20%EB%AA%A8%EC%A7%91%EC%9A%94%EA%B0%95(%EB%8F%99%EC%9D%98%EB%8C%80).pdf
https://www.deu.ac.kr/www/deu-college-of-humanities.do
https://www.deu.ac.kr/www/deu-college-of-cne.do
https://www.deu.ac.kr/www/deu-colleage-future-convergence.do
https://www.deu.ac.kr/www/deu-college-of-korean-medicine.do
https://www.deu.ac.kr/www/deu-college-of-arts.do
https://www.deu.ac.kr/www/deu-college-of-liberal-studies.do
https://www.deu.ac.kr/www/deu-college-of-global.do
https://sanhak.deu.ac.kr/rnd/index.do
https://dess.deu.ac.kr/?mid=Page6
https://www.deu.ac.kr/www/academicguide.do
https://www.deu.ac.kr/www/deu-rotc.do
https://www.deu.ac.kr/www/deu-reservists.do
https://www.deu.ac.kr/www/deu-collabo-intro.do
https://www.isic.co.kr/dongeui/dongeuiIndex.jsp
https://www.deu.ac.kr/www/deu-culture.do
https://www.deu.ac.kr/www/deu-benefits.do
https://dess.deu.ac.kr/?mid=Page2
https://dess.deu.ac.kr/?mid=Page9
https://dess.deu.ac.kr/?mid=Page5
https://dess.deu.ac.kr/?mid=Page7
https://dess.deu.ac.kr/?mid=Page10
https://dess.deu.ac.kr/?mid=Page13
https://dess.deu.ac.kr/?mid=Page4
https://koreanl.deu.ac.kr/
https://china.deu.ac.kr/
https://japan.deu.ac.kr/
https://english.deu.ac.kr/
https://lis.deu.ac.kr/
https://lifelonged.deu.ac.kr/
https://psychology.deu.ac.kr/
https://childfamily.deu.ac.kr/
https://ece.deu.ac.kr/
https://ad.deu.ac.kr/
https://massmedia.deu.ac.kr/
https://law.deu.ac.kr/
https://police2001.deu.ac.kr/
https://fire.deu.ac.kr/
https://pap.deu.ac.kr/
https://socialwelfare.deu.ac.kr/
https://dcc.deu.ac.kr/
https://banin.deu.ac.kr/
https://deuhome.deu.ac.kr/fre/index.do
https://trade.deu.ac.kr/
https://dm.deu.ac.kr/
https://logistics.deu.ac.kr/
https://eim.deu.ac.kr/eim/index.do
https://busunessadministration.deu.ac.kr/
https://mis.deu.ac.kr/
https://ebiz.deu.ac.kr/
https://newtour.deu.ac.kr/
https://hotel.deu.ac.kr/
https://neweatingout.deu.ac.kr/
https://shp.deu.ac.kr/
https://sei.deu.ac.kr/sei/index.do
https://bb.deu.ac.kr/bb/index.do
https://llc.deu.ac.kr/llc/index.do
https://rdm.deu.ac.kr/rdm/index.do
https://multicounsel.deu.ac.kr/
https://seniorsp.deu.ac.kr/
https://nursing.deu.ac.kr/
https://1cls.deu.ac.kr/
https://dental.deu.ac.kr/
https://radiology.deu.ac.kr/
https://hcm1.deu.ac.kr/
https://pt.deu.ac.kr/
https://fn.deu.ac.kr/
https://ems.deu.ac.kr/
https://omc.deu.ac.kr/
https://nme.deu.ac.kr/
https://mecha.deu.ac.kr/
https://automotive-engineering.deu.ac.kr/
https://naoe.deu.ac.kr/
https://mse.deu.ac.kr/
https://deuproarchi.deu.ac.kr/
https://archieng.deu.ac.kr/
https://civil.deu.ac.kr/
https://urban.deu.ac.kr/
https://env.deu.ac.kr/
https://cheng.deu.ac.kr/
https://dce.deu.ac.kr/
https://biotech.deu.ac.kr/
https://biopharm.deu.ac.kr/
https://efood.deu.ac.kr/
https://hsde.deu.ac.kr/
https://pite.deu.ac.kr/
https://pdm.deu.ac.kr/
https://elec.deu.ac.kr/
https://ee.deu.ac.kr/
https://energy.deu.ac.kr/
https://futuremobility.deu.ac.kr/
https://swcc.deu.ac.kr/
https://sw.deu.ac.kr/
https://music.deu.ac.kr/
https://designart.deu.ac.kr/
https://fashion.deu.ac.kr/
https://deptpe.deu.ac.kr/
https://deuhome.deu.ac.kr/leisure/index.do
https://tkd.deu.ac.kr/
https://sportscoaching.deu.ac.kr/
https://cinema.deu.ac.kr/
https://kbeauty.deu.ac.kr/
""".strip().splitlines()

SEED_URLS.extend(_make_doc_seed(url) for url in _DOC_SEED_URLS)
