def get_category_from_utterance(utterance: str):
    if "수강" in utterance:
        return "수강"
    if "장학" in utterance:
        return "장학"
    if "기숙사" in utterance:
        return "기숙사"
    return None

def get_title_by_category(category: str):
    title_map = {
        "수강": "수강신청 안내",
        "장학": "장학금 안내",
        "기숙사": "기숙사 안내",
    }
    return title_map.get(category, "동의대학교 안내")


def get_quick_replies_by_category(category: str):
    button_map = {
        "수강": [
            {"label": "수강신청", "action": "message", "messageText": "수강신청 언제야?"},
            {"label": "수강정정", "action": "message", "messageText": "수강정정 기간 알려줘"},
            {"label": "학사일정", "action": "message", "messageText": "학사일정 알려줘"},
        ],
        "장학": [
            {"label": "장학금", "action": "message", "messageText": "장학금 신청 방법 알려줘"},
            {"label": "국가장학", "action": "message", "messageText": "국가장학금 신청 기간 알려줘"},
            {"label": "성적장학", "action": "message", "messageText": "성적장학금 기준 알려줘"},
        ],
        "기숙사": [
            {"label": "기숙사", "action": "message", "messageText": "기숙사 신청 언제야?"},
            {"label": "비용", "action": "message", "messageText": "기숙사 비용 알려줘"},
            {"label": "입사안내", "action": "message", "messageText": "기숙사 입사 안내 알려줘"},
        ],
    }

    return button_map.get(category, [
        {"label": "수강신청", "action": "message", "messageText": "수강신청 언제야?"},
        {"label": "장학금", "action": "message", "messageText": "장학금 신청 방법 알려줘"},
        {"label": "기숙사", "action": "message", "messageText": "기숙사 신청 언제야?"},
    ])


def get_link_url_by_category(category: str):
    link_map = {
        "수강": "https://dess.deu.ac.kr/",
        "장학": "https://www.deu.ac.kr/www/boardview/12/1",
        "기숙사": "https://dorm.deu.ac.kr/",
    }

    return link_map.get(category, "https://www.deu.ac.kr/")