import unittest

from backend.app.main import app
from backend.app.utils.intent_classifier import PrimaryIntentClassifier


class AppBehaviorTest(unittest.TestCase):
    def test_kakao_webhook_route_is_registered_once(self) -> None:
        webhook_routes = [
            route
            for route in app.routes
            if getattr(route, "path", None) == "/api/kakao/webhook"
        ]

        self.assertEqual(len(webhook_routes), 1)

    def test_primary_intent_classifier_distinguishes_general_and_info(self) -> None:
        classifier = PrimaryIntentClassifier()

        self.assertEqual(classifier.classify("안녕"), "GENERAL")
        self.assertEqual(classifier.classify("수강신청 기간 알려줘"), "INFO")


if __name__ == "__main__":
    unittest.main()
