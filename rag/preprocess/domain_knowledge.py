"""도메인 지식 정의
- 엔티티 스키마: 주요 엔티티 그룹과 대표 키워드 정의
- 엔티티 사전: 각 엔티티 그룹별 키워드 목록
- 자주 묻는 질문 패턴: FAQ 유형별 의도, 엔티티 조합, 예시 질문 정의
"""

from __future__ import annotations

DOMAIN_RULES: dict[str, dict[str, object]] = {
    "academic": {
        "keywords": ["학사", "학사일정", "휴학", "복학", "전과", "출석", "보강", "계절학기"],
        "synonyms": {"학사": ["학사공지", "학사 안내"], "휴학": ["휴학신청"], "복학": ["복학신청"]},
        "intent_boost": "RAG",
        "category": "academic",
        "source_boosts": ["academic_notice", "notice", "institution"],
    },
    "course": {
        "keywords": ["수강", "수강신청", "수업", "강의", "정정", "강의계획서", "시간표"],
        "synonyms": {"수강": ["수강신청", "강의신청", "수업신청"], "수업": ["강의"]},
        "intent_boost": "RAG",
        "category": "course",
        "source_boosts": ["academic_notice", "department", "institution"],
    },
    "grade": {
        "keywords": ["성적", "학점", "평점", "GPA", "출석"],
        "synonyms": {"성적": ["학점", "평점", "GPA"]},
        "intent_boost": "RAG",
        "category": "grade",
        "source_boosts": ["academic_notice", "institution"],
    },
    "graduation": {
        "keywords": ["졸업", "졸업요건", "졸업학점", "논문", "학위"],
        "synonyms": {"졸업": ["졸업요건", "졸업학점"]},
        "intent_boost": "RAG",
        "category": "graduation",
        "source_boosts": ["academic_notice", "department", "institution"],
    },
    "scholarship": {
        "keywords": ["장학", "장학금", "국가장학", "교내장학", "근로장학", "학자금"],
        "synonyms": {"장학": ["장학금", "등록금 지원", "학비 지원"], "국가장학": ["국가장학금"]},
        "intent_boost": "RAG",
        "category": "scholarship",
        "source_boosts": ["scholarship", "notice"],
    },
    "tuition": {
        "keywords": ["등록금", "수업료", "학비", "납부", "고지서", "분납"],
        "synonyms": {"등록금": ["수업료", "학비"], "고지서": ["등록금 고지서"]},
        "intent_boost": "RAG",
        "category": "tuition",
        "source_boosts": ["academic_notice", "institution", "notice"],
    },
    "career": {
        "keywords": ["취업", "진로", "현장실습", "IPP", "일학습", "인턴", "취업지원센터"],
        "synonyms": {"현장실습": ["IPP", "인턴"], "취업": ["취업지원", "진로"]},
        "intent_boost": "RAG",
        "category": "career",
        "source_boosts": ["job", "department", "institution"],
    },
    "admission": {
        "keywords": ["입학", "입시", "신입생", "편입", "모집요강"],
        "synonyms": {"입학": ["입시"], "편입": ["편입학"]},
        "intent_boost": "RAG",
        "category": "admission",
        "source_boosts": ["admission", "notice"],
    },
    "notice": {
        "keywords": ["공지", "공지사항", "게시판", "안내", "모집", "공고"],
        "synonyms": {"공지": ["공지사항", "게시글"]},
        "intent_boost": "RAG",
        "category": "notice",
        "source_boosts": ["notice", "academic_notice", "external_notice"],
    },
    "department_major": {
        "keywords": ["학과", "전공", "학부", "단과대학", "컴퓨터공학과", "학과사무실"],
        "synonyms": {"컴퓨터공학과": ["컴공", "컴퓨터", "computer", "computer engineering"]},
        "intent_boost": "RAG",
        "category": "department",
        "source_boosts": ["department"],
    },
    "faculty_staff": {
        "keywords": ["교수", "교수님", "교직원", "연구실", "이메일", "전화번호"],
        "synonyms": {"교수": ["교수님"], "전화번호": ["연락처"]},
        "intent_boost": "RAG",
        "category": "faculty",
        "source_boosts": ["department", "institution"],
    },
    "office_admin": {
        "keywords": ["부서", "행정부서", "교무처", "학생지원팀", "입학처", "장학팀", "행정실"],
        "synonyms": {"행정실": ["학과사무실"], "부서": ["행정부서"]},
        "intent_boost": "RAG",
        "category": "office",
        "source_boosts": ["institution", "department"],
    },
    "campus_facility": {
        "keywords": ["캠퍼스", "건물", "건물번호", "시설", "위치", "정보공학관", "수덕전", "호관", "라운지"],
        "synonyms": {"정보공학관": ["23번 건물"], "수덕전": ["수덕관"], "위치": ["어디"]},
        "intent_boost": "RAG",
        "category": "facility",
        "source_boosts": ["institution", "department", "static", "facility"],
    },
    "library": {
        "keywords": ["도서관", "중앙도서관", "열람실", "자료실", "운영시간"],
        "synonyms": {"도서관": ["중앙도서관", "열람실"]},
        "intent_boost": "RAG",
        "category": "library",
        "source_boosts": ["institution", "library"],
    },
    "cafeteria": {
        "keywords": ["학생식당", "식당", "학식", "식단", "메뉴", "오늘 밥"],
        "synonyms": {"학생식당": ["학식", "식단", "오늘 밥"], "식단": ["메뉴"]},
        "intent_boost": "RAG",
        "category": "cafeteria",
        "source_boosts": ["institution", "static"],
    },
    "shuttle": {
        "keywords": ["통학버스", "셔틀", "셔틀버스", "통버", "버스", "시간표", "노선"],
        "synonyms": {"통학버스": ["통버", "셔틀", "셔틀버스"], "노선": ["버스노선"]},
        "intent_boost": "RAG",
        "category": "shuttle",
        "source_boosts": ["institution", "notice"],
    },
    "dormitory": {
        "keywords": ["기숙사", "생활관", "효민생활관", "제2효민생활관", "입사"],
        "synonyms": {"기숙사": ["생활관"], "제2효민생활관": ["2효민생활관"]},
        "intent_boost": "RAG",
        "category": "dormitory",
        "source_boosts": ["dormitory", "notice"],
    },
    "club_activity": {
        "keywords": ["동아리", "학생활동", "비교과", "마일리지", "학생회"],
        "synonyms": {"동아리": ["학생동아리"], "비교과": ["비교과프로그램"]},
        "intent_boost": "RAG",
        "category": "club_activity",
        "source_boosts": ["department", "institution", "notice"],
    },
    "international": {
        "keywords": ["국제교류", "교환학생", "어학연수", "유학생", "외국인"],
        "synonyms": {"교환학생": ["국제교류"], "유학생": ["외국인학생"]},
        "intent_boost": "RAG",
        "category": "international",
        "source_boosts": ["notice", "institution"],
    },
    "counseling_support": {
        "keywords": ["상담", "학생지원", "장애학생", "인권센터", "심리"],
        "synonyms": {"상담": ["심리상담"], "학생지원": ["학생지원팀"]},
        "intent_boost": "RAG",
        "category": "support",
        "source_boosts": ["institution", "notice"],
    },
    "military": {
        "keywords": ["예비군", "병무", "군휴학", "훈련"],
        "synonyms": {"예비군": ["예비군훈련"], "병무": ["군휴학"]},
        "intent_boost": "RAG",
        "category": "military",
        "source_boosts": ["notice", "institution"],
    },
    "certificate_civil": {
        "keywords": ["증명서", "민원", "발급", "재학증명서", "졸업증명서"],
        "synonyms": {"증명서": ["민원", "증명 발급"], "발급": ["출력"]},
        "intent_boost": "RAG",
        "category": "certificate",
        "source_boosts": ["institution", "notice"],
    },
    "attachment_form": {
        "keywords": ["첨부파일", "PDF", "pdf", "서식", "신청서", "양식", "파일"],
        "synonyms": {"첨부파일": ["PDF", "파일"], "서식": ["양식", "신청서"]},
        "intent_boost": "RAG",
        "category": "attachment",
        "source_boosts": ["notice", "academic_notice", "department"],
    },
}

ENTITY_ALIASES: dict[str, list[str]] = {
    "동의대학교": ["동의대", "DEU", "deu"],
    "컴퓨터공학과": ["컴공", "컴퓨터", "computer", "computer engineering"],
    "정보공학관": ["23번 건물", "23번건물", "정보관"],
    "수덕전": ["수덕관"],
    "통학버스": ["통버", "셔틀", "셔틀버스"],
    "학생식당": ["학식", "식단", "오늘 밥", "메뉴"],
    "기숙사": ["생활관", "효민생활관", "제2효민생활관"],
    "장학금": ["장학", "국가장학", "교내장학", "근로장학", "학자금"],
    "수강신청": ["수강", "강의신청", "수업신청"],
}

DOMAIN_BLACKLIST = {"정보", "안내", "내용", "관련", "이름", "방법", "기간"}

ENTITY_SCHEMA: dict[str, list[str]] = {
    "category": ["학사", "장학", "등록", "졸업", "휴학", "복학", "수강", "기숙사", "비교과", "국제"],
    "target": ["신입생", "재학생", "복학생", "편입생", "대학원생", "외국인", "졸업예정자"],
    "time": ["오늘", "이번학기", "1학기", "2학기", "상반기", "하반기", "마감", "기한", "기간", "일정"],
    "department": ["교무처", "학생지원팀", "입학처", "국제교류원", "장학팀", "학과사무실"],
    "action": ["신청", "확인", "제출", "조회", "변경", "취소", "납부", "연장", "문의"],
}

ENTITY_SCHEMA.setdefault("domain", list(DOMAIN_RULES))

ENTITY_LEXICON: dict[str, list[str]] = {
    "학사": ["학사", "수강", "강의", "성적", "학점"],
    "장학": ["장학", "장학금", "국가장학", "근로장학"],
    "등록": ["등록", "등록금", "납부", "고지서"],
    "졸업": ["졸업", "졸업요건", "졸업학점", "논문"],
    "휴학": ["휴학", "군휴학", "일반휴학"],
    "복학": ["복학", "복학신청"],
    "수강": ["수강", "수강신청", "정정"],
    "기숙사": ["기숙사", "생활관"],
    "비교과": ["비교과", "프로그램", "특강"],
    "국제": ["국제", "교환학생", "어학"],
    "신입생": ["신입생", "새내기"],
    "재학생": ["재학생"],
    "복학생": ["복학생"],
    "편입생": ["편입생"],
    "대학원생": ["대학원생"],
    "외국인": ["외국인", "유학생"],
    "졸업예정자": ["졸업예정", "졸업예정자"],
    "교무처": ["교무처"],
    "학생지원팀": ["학생지원팀"],
    "입학처": ["입학처"],
    "국제교류원": ["국제교류원"],
    "장학팀": ["장학팀"],
    "학과사무실": ["학과사무실", "학과", "학부"],
    "신청": ["신청", "접수", "지원"],
    "확인": ["확인", "체크"],
    "제출": ["제출", "업로드"],
    "조회": ["조회", "열람"],
    "변경": ["변경", "수정"],
    "취소": ["취소", "철회"],
    "납부": ["납부", "입금"],
    "연장": ["연장"],
    "문의": ["문의", "질문"],
    "기간": ["기간", "일정", "언제", "마감", "기한", "까지"],
    "시점": ["오늘", "내일", "이번", "언제"],
}

ENTITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "장학금": ("학자금", "학자금 지원"),
    "국가장학": ("국가장학금", "학자금 지원"),
    "등록금": ("수업료", "학비"),
    "기숙사": ("생활관",),
    "생활관": ("기숙사",),
    "수강신청": ("강의신청",),
    "교환학생": ("국제교류",),
}
for canonical, aliases in ENTITY_ALIASES.items():
    ENTITY_SYNONYMS[canonical] = tuple(dict.fromkeys((*ENTITY_SYNONYMS.get(canonical, ()), *aliases)))
    for alias in aliases:
        ENTITY_SYNONYMS.setdefault(alias, (canonical,))

CATEGORY_BY_REWRITE_ENTITY: dict[str, str] = {
    "휴학": "휴학",
    "복학": "복학",
    "장학금": "장학",
    "장학": "장학",
    "등록금": "등록",
    "고지서": "등록",
    "수강신청": "수강",
    "수강": "수강",
    "학사공지": "학사",
    "졸업": "졸업",
    "기숙사": "기숙사",
    "생활관": "기숙사",
}

REWRITE_ENTITY_SURFACES: dict[str, tuple[str, ...]] = {
    "휴학": ("휴학", "군휴학", "일반휴학"),
    "복학": ("복학", "복학신청"),
    "장학금": ("장학금", "국가장학", "근로장학"),
    "장학": ("장학",),
    "등록금": ("등록금", "수업료", "학비"),
    "고지서": ("고지서",),
    "수강신청": ("수강신청", "강의신청"),
    "수강": ("수강", "강의"),
    "학사공지": ("학사공지",),
    "졸업": ("졸업", "졸업요건", "졸업학점", "논문"),
    "기숙사": ("기숙사",),
    "생활관": ("생활관",),
}
for domain_name, rule in DOMAIN_RULES.items():
    keywords = tuple(str(value) for value in rule.get("keywords", []) if value)
    category = str(rule.get("category") or domain_name)
    ENTITY_LEXICON.setdefault(category, [])
    ENTITY_LEXICON[category] = list(dict.fromkeys([*ENTITY_LEXICON[category], *keywords]))

REWRITE_ENTITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "장학금": ("국가장학", "근로장학", "학자금지원"),
    "등록금": ("수업료", "학비"),
    "수강신청": ("강의신청",),
    "기숙사": ("생활관",),
    "생활관": ("기숙사",),
}
for rule in DOMAIN_RULES.values():
    synonyms = rule.get("synonyms", {})
    if isinstance(synonyms, dict):
        for key, values in synonyms.items():
            REWRITE_ENTITY_SYNONYMS[key] = tuple(
                dict.fromkeys([*REWRITE_ENTITY_SYNONYMS.get(key, ()), *[str(value) for value in values]])
            )

REWRITE_ENTITY_GROUPS: dict[str, tuple[str, ...]] = {
    "장학": ("장학금", "장학"),
    "등록": ("등록금", "고지서"),
}

GENERIC_INTENT_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "기간": ("기간", "일정", "마감일"),
    "방법": ("방법", "절차"),
    "확인": ("조회",),
    "신청": ("신청", "접수"),
    "자격": ("자격", "대상"),
    "서류": ("서류", "제출서류"),
}

CONDITIONAL_EXPANSION_RULES: tuple[dict[str, tuple[str, ...]], ...] = (
    {
        "intents": ("방법",),
        "entities": ("휴학",),
        "entity_groups": (),
        "expansions": ("신청", "절차", "제출처", "필요서류"),
    },
    {
        "intents": ("신청",),
        "entities": ("휴학",),
        "entity_groups": (),
        "expansions": ("신청", "접수", "제출처", "필요서류"),
    },
    {
        "intents": ("기간",),
        "entities": ("휴학",),
        "entity_groups": (),
        "expansions": ("신청기간", "일정", "마감일"),
    },
    {
        "intents": ("확인",),
        "entities": (),
        "entity_groups": ("장학",),
        "expansions": ("조회", "선발결과", "지급일"),
    },
    {
        "intents": ("확인",),
        "entities": (),
        "entity_groups": ("등록",),
        "expansions": ("고지서", "조회", "납부금액"),
    },
)

EXPANSIONS_REQUIRING_SOURCE_TERM: dict[str, str] = {
    "납부방법": "납부",
}

FREQUENT_QUESTION_PATTERNS: list[dict[str, object]] = [
    {
        "id": "registration_deadline",
        "intent": "기간확인",
        "entities": ["category:수강", "action:신청", "time:기간"],
        "examples": ["수강신청 언제까지야?", "정정기간 마감일 알려줘", "이번 학기 신청 일정이 궁금해"],
    },
    {
        "id": "scholarship_apply",
        "intent": "방법안내",
        "entities": ["category:장학", "action:신청", "target:재학생"],
        "examples": ["장학금 신청 방법 알려줘", "국가장학 신청 어디서 해?", "장학 서류 제출처가 어디야?"],
    },
    {
        "id": "tuition_payment",
        "intent": "절차확인",
        "entities": ["category:등록", "action:납부"],
        "examples": ["등록금 납부 기간 알려줘", "등록금 고지서 조회 어디서 해?", "등록금 분할 납부 가능해?"],
    },
    {
        "id": "graduation_requirement",
        "intent": "요건확인",
        "entities": ["category:졸업", "target:졸업예정자"],
        "examples": ["졸업요건 뭐 남았는지 확인하고 싶어", "졸업학점 기준 알려줘", "졸업논문 제출 기한이 언제야?"],
    },
    {
        "id": "leave_and_return",
        "intent": "절차확인",
        "entities": ["category:휴학", "category:복학", "action:신청"],
        "examples": ["휴학 신청 기간 언제야?", "복학 신청 어디서 해?", "군휴학 복학 절차 알려줘"],
    },
]
