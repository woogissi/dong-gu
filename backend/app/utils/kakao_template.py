def kakao_response(text: str):
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ],
            "quickReplies": [
                {
                    "label": "수강신청",
                    "action": "message",
                    "messageText": "수강신청 언제야?"
                },
                {
                    "label": "장학금",
                    "action": "message",
                    "messageText": "장학금 신청 방법 알려줘"
                },
                {
                    "label": "기숙사",
                    "action": "message",
                    "messageText": "기숙사 신청 언제야?"
                }
            ]
        }
    }