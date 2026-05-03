import requests


def kakao_callback(callback_url: str, response_body: dict) -> None:
    if not callback_url:
        return

    requests.post(
        callback_url,
        json=response_body,
        timeout=5,
    )