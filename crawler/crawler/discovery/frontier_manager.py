# crawler/discovery/frontier_manager.py

from collections import deque                   # 큐 사용을 위함
from urllib.parse import urldefrag, urlparse    # url 사용을 위한 라이브러리, 현재는 fragment제거, url 분리(scheme: https / host(netloc): www.deu.ac.kr / path: /www/index.do)


class FrontierManager:
    def __init__(self, allowed_hosts: set[str], max_depth: int = 2):    # allowed_hosts : 허용 도메인들, max_depth : 깊이
        self.allowed_hosts = allowed_hosts
        self.max_depth = max_depth
        self.queue = deque()        # 큐 구성 (url, 현재 깊이, url출처)
        self.visited = set()        # 방문 url 저장 집합(중복검사 용이)
        self.queued = set()

    def canonicalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)     # 예를들어 url이 ("https://abc.com/page", "section1") 일 경우 뒤의 fragment는 지우고 앞의 url만 저장
        url = url.strip()
        parsed = urlparse(url)
        if parsed.path == "/" and not parsed.query:
            return url.rstrip("/")
        return url

    def is_allowed(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()     # 파싱된 url의 host부분만 추출
        return host in self.allowed_hosts       # host가 허용 도메인에 있으면 True 아니면 false

    def add_url(self, url: str, depth: int, discovered_from: str | None = None) -> bool:
        url = self.canonicalize_url(url)

        if depth > self.max_depth:  # 현재 깊이가 허용깊이보다 큰지 확인
            return False

        if not self.is_allowed(url):# 허용 도메인인지 확인
            return False

        if url in self.visited:     # 방문한 url인지 확인
            return False

        if url in self.queued:
            return False

        self.queue.append((url, depth, discovered_from))
        self.queued.add(url)
        return True                 # 큐에 저장 성공시 True 반환

    def mark_visited(self, url: str) -> None:
        self.visited.add(self.canonicalize_url(url))    # 방문 주소 저장

    def pop_next(self):             # 다음 방문할 사이트 pop
        if not self.queue:
            return None
        item = self.queue.popleft()
        self.queued.discard(item[0])
        return item

    def has_next(self) -> bool:     # 큐에 방문할 사이트 남아있는지 확인
        return len(self.queue) > 0

    def stats(self) -> dict:        # 로그용 현재 상태 반환
        return {
            "queued": len(self.queue),      #큐에 대기중인 사이트 개수
            "queued_unique": len(self.queued),
            "visited": len(self.visited),   #방문한 사이트 개수
            "max_depth": self.max_depth,    #현재 최대 깊이
        }
