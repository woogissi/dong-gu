def default_quick_replies():
    return [
        {"label": "수강신청", "action": "message", "messageText": "수강신청 언제야?"},
        {"label": "장학금", "action": "message", "messageText": "장학금 신청 방법 알려줘"},
        {"label": "기숙사", "action": "message", "messageText": "기숙사 신청 언제야?"},
    ]


def kakao_response(text: str, quick_replies=None):
    if not quick_replies:
        quick_replies = default_quick_replies()

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (text or "답변을 생성하지 못했습니다.")[:500]
                    }
                }
            ],
            "quickReplies": quick_replies[:3]
        }
    }


def kakao_text_card(title: str, description: str, link_url: str, quick_replies=None):
    if not quick_replies:
        quick_replies = default_quick_replies()

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "textCard": {
                        "title": (title or "동의대학교 안내")[:50],
                        "description": (
                            description or "자세한 내용은 아래 버튼을 통해 확인해주세요."
                        )[:300],
                        "buttons": [
                            {
                                "action": "webLink",
                                "label": "사이트 바로가기",
                                "webLinkUrl": link_url or "https://www.deu.ac.kr/"
                            }
                        ]
                    }
                }
            ],
            "quickReplies": quick_replies[:3]
        }
    }

def kakao_mixed_response(
    text: str,
    title: str,
    link_url: str,
    quick_replies=None,
):
    if not quick_replies:
        quick_replies = default_quick_replies()

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (text or "답변을 생성하지 못했습니다.")[:500]
                    }
                },
                {
                    "textCard": {
                        "title": (title or "동의대학교 안내")[:50],
                        "description": "자세한 내용은 아래 버튼을 통해 확인해주세요.",
                        "buttons": [
                            {
                                "action": "webLink",
                                "label": "사이트 바로가기",
                                "webLinkUrl": link_url or "https://www.deu.ac.kr/"
                            }
                        ]
                    }
                }
            ],
            "quickReplies": quick_replies[:3]
        }
    }