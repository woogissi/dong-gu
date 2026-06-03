"""골드셋 평가 매칭 함수(`_check_hit`)의 bare-도메인 가드 회귀 테스트.

bare 도메인 gold_url(예: https://www.deu.ac.kr)이 같은 도메인의 무관한 페이지까지
Hit으로 인정하던 과대매칭(false positive)을 차단했는지 검증한다.
document_id 기반 매칭과 path 있는 URL 매칭은 그대로 동작해야 한다.
"""

from rag.evaluation.goldset.run_goldset_eval import _check_hit, _url_has_path, _is_refusal


def test_url_has_path_rejects_bare_domain():
    assert _url_has_path("https://www.deu.ac.kr") is False
    assert _url_has_path("https://dorm.deu.ac.kr") is False
    assert _url_has_path("https://lib.deu.ac.kr/") is False


def test_url_has_path_accepts_pathful_url():
    assert _url_has_path("https://www.deu.ac.kr/www/phone.do") is True
    assert _url_has_path("https://dorm.deu.ac.kr/30/3010.do") is True


def test_bare_domain_url_does_not_overmatch():
    """bare 도메인 gold는 같은 도메인의 무관 페이지를 Hit으로 인정하면 안 된다."""
    gold = [{"document_id": "", "url": "https://www.deu.ac.kr"}]
    # 전혀 무관한 www.deu.ac.kr 하위 페이지
    assert _check_hit("static_x", "https://www.deu.ac.kr/www/deu-dining-hall.do", "static_x#0", gold) is False


def test_document_id_match_still_works():
    gold = [{"document_id": "static_52634667972a5f32", "url": "https://www.deu.ac.kr"}]
    # bare 도메인 URL이라도 doc_id가 일치하면 Hit
    assert _check_hit("static_52634667972a5f32", "https://www.deu.ac.kr/www/phone.do?x=1", "c#0", gold) is True


def test_chunk_id_prefix_match_still_works():
    gold = [{"document_id": "deu_notice_123", "url": ""}]
    assert _check_hit("other", "", "deu_notice_123#chunk0", gold) is True


def test_pathful_url_substring_match_still_works():
    gold = [{"document_id": "", "url": "https://www.deu.ac.kr/www/deu-campus-map.do"}]
    assert _check_hit("anydoc", "https://www.deu.ac.kr/www/deu-campus-map.do", "c#0", gold) is True
    # 같은 도메인이지만 경로가 다르면 불일치
    assert _check_hit("anydoc", "https://www.deu.ac.kr/www/deu-other.do", "c#0", gold) is False


def test_refusal_detects_honest_no_info_variants():
    # '포함되어 있지 않습니다'/'언급은 없습니다' 같은 정직한 정보없음 표현도 거절로 잡아야 한다(G016).
    answer = (
        "제공된 문서에서는 장학금 지급일에 대한 구체적인 정보가 포함되어 있지 않습니다. "
        "지급일에 대한 언급은 없습니다. 추가적인 정보가 필요하시면 관련 부서에 문의하시기 바랍니다."
    )
    assert _is_refusal(answer) is True


def test_partial_answer_is_not_refusal():
    # 부정 문장이 섞여 있어도 그 외 구체 정보가 남으면 부분답변(거절 아님)이다(G030).
    answer = (
        "제공된 문서에서 학점포기와 관련된 정보는 찾을 수 없었습니다. "
        "다만, 성적포기 제도는 폐지되었으며 학점을 제외한 성적증명서 발급이 불가하다는 내용이 있습니다."
    )
    assert _is_refusal(answer) is False


def test_pure_refusal_and_normal_answer():
    assert _is_refusal("제공된 문서에서 관련 정보를 찾지 못했습니다.") is True
    assert _is_refusal("성적 이의신청은 6월 30일부터 7월 6일까지 담당 교원에게 요청하면 됩니다.") is False
    assert _is_refusal("") is False
