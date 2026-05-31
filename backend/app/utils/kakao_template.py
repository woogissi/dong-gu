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

    outputs = [
        {
            "simpleText": {
                "text": (text or "\ub2f5\ubcc0\uc744 \uc0dd\uc131\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.")[:500]
            }
        }
    ]

    # \uc2e4\uc81c \uac80\uc0c9\ub41c \ubb38\uc11c URL\uc774 \uc788\uc744 \ub54c\ub9cc \uc0ac\uc774\ud2b8 \ubc14\ub85c\uac00\uae30 \ubc84\ud2bc \ucd94\uac00
    if link_url:
        outputs.append(
            {
                "textCard": {
                    "title": (title or "\ub3d9\uc758\ub300\ud559\uad50 \uc548\ub0b4")[:50],
                    "description": "\uc790\uc138\ud55c \ub0b4\uc6a9\uc740 \uc544\ub798 \ubc84\ud2bc\uc5d0\uc11c \ud655\uc778\ud574 \uc8fc\uc138\uc694.",
                    "buttons": [
                        {
                            "action": "webLink",
                            "label": "\uc0ac\uc774\ud2b8 \ubc14\ub85c\uac00\uae30",
                            "webLinkUrl": link_url
                        }
                    ]
                }
            }
        )

    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": quick_replies[:3]
        }
    }
