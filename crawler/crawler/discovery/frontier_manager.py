# crawler/discovery/frontier_manager.py

from collections import deque
from urllib.parse import urldefrag, urlparse


class FrontierManager:
    def __init__(self, allowed_hosts: set[str], max_depth: int = 2):
        self.allowed_hosts = allowed_hosts
        self.max_depth = max_depth
        self.queue = deque()
        self.visited = set()

    def canonicalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)
        return url.strip()

    def is_allowed(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in self.allowed_hosts

    def add_url(self, url: str, depth: int, discovered_from: str | None = None) -> bool:
        url = self.canonicalize_url(url)

        if depth > self.max_depth:
            return False

        if not self.is_allowed(url):
            return False

        if url in self.visited:
            return False

        # 큐 중복 방지
        for queued_url, _, _ in self.queue:
            if queued_url == url:
                return False

        self.queue.append((url, depth, discovered_from))
        return True

    def mark_visited(self, url: str) -> None:
        self.visited.add(self.canonicalize_url(url))

    def pop_next(self):
        if not self.queue:
            return None
        return self.queue.popleft()

    def has_next(self) -> bool:
        return len(self.queue) > 0

    def stats(self) -> dict:
        return {
            "queued": len(self.queue),
            "visited": len(self.visited),
            "max_depth": self.max_depth,
        }