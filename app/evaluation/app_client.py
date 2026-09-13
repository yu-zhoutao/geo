from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
from typing import Any, TypeVar
import urllib.error
import urllib.request


class EvaluationApiError(RuntimeError):
    pass


DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_REQUEST_MAX_ATTEMPTS = 3
DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS = 0.25
T = TypeVar('T')


class EvaluationAppClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_REQUEST_MAX_ATTEMPTS,
        retry_backoff_seconds: float = DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be positive')
        if max_attempts <= 0:
            raise ValueError('max_attempts must be positive')
        if retry_backoff_seconds < 0:
            raise ValueError('retry_backoff_seconds must be non-negative')
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds

    async def create_session(self) -> dict[str, Any]:
        return await self._request_json('POST', '/api/sessions')

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request_json('GET', f'/api/sessions/{session_id}')

    async def update_data_directories(self, session_id: str, items: list[dict[str, object]]) -> dict[str, Any]:
        return await self._request_json(
            'PUT',
            f'/api/sessions/{session_id}/data-directories',
            {'items': items},
        )

    async def submit_message(self, session_id: str, text: str) -> dict[str, Any]:
        return await self._request_json('POST', f'/api/sessions/{session_id}/messages', {'text': text})

    async def interrupt_session(self, session_id: str) -> None:
        await self._request_json('POST', f'/api/sessions/{session_id}/interrupt')

    async def answer_question(
        self,
        session_id: str,
        question_id: str,
        *,
        answer: str | None = None,
        answers: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            'POST',
            f'/api/sessions/{session_id}/questions/{question_id}/answers',
            {'answer': answer, 'answers': answers or []},
        )

    async def export_session_archive(self, session_id: str) -> dict[str, Any]:
        return await self._request_json('GET', f'/api/sessions/{session_id}/archive')

    async def fetch_artifact_content(self, session_id: str, artifact_id: str) -> bytes:
        path = f'/api/sessions/{session_id}/artifacts/{artifact_id}/content'
        return await self._request_with_timeout_retries(
            lambda: self._request_bytes_sync('GET', path),
            description=f'GET {path}',
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request_with_timeout_retries(
            lambda: self._request_json_sync(method, path, payload),
            description=f'{method} {path}',
        )

    async def _request_with_timeout_retries(self, operation: Callable[[], T], *, description: str) -> T:
        last_timeout: TimeoutError | None = None
        for attempt_index in range(self.max_attempts):
            try:
                return await asyncio.to_thread(operation)
            except TimeoutError as exc:
                last_timeout = exc
                if attempt_index + 1 >= self.max_attempts:
                    break
                await asyncio.sleep(self.retry_backoff_seconds)
        raise EvaluationApiError(
            f'{description} timed out after {self.max_attempts} attempts '
            f'with {self.timeout_seconds:g}s request timeout'
        ) from last_timeout

    def _request_json_sync(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data: bytes | None = None
        headers: dict[str, str] = {'Accept': 'application/json'}
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(
            f'{self.base_url}{path}',
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status == 204:
                    return {}
                raw = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise EvaluationApiError(f'{method} {path} failed with {exc.code}: {body}') from exc
        except urllib.error.URLError as exc:
            raise EvaluationApiError(f'{method} {path} failed: {exc}') from exc
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise EvaluationApiError(f'{method} {path} returned a non-object JSON payload')
        return parsed

    def _request_bytes_sync(self, method: str, path: str) -> bytes:
        request = urllib.request.Request(
            f'{self.base_url}{path}',
            headers={'Accept': '*/*'},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise EvaluationApiError(f'{method} {path} failed with {exc.code}: {body}') from exc
        except urllib.error.URLError as exc:
            raise EvaluationApiError(f'{method} {path} failed: {exc}') from exc
