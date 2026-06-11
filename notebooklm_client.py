"""
NotebookLM 연동 클라이언트.
PaperRadar에서 수집한 논문 URL을 NotebookLM 노트북에 소스로 자동 추가.

사전 조건 (최초 1회):
    notebooklm login   ← Google 계정 브라우저 로그인
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

NOTEBOOK_TITLE = "PaperRadar — AI/DT 논문"


NOTEBOOK_LIMIT = 50


def _notebook_title(base: str, idx: int) -> str:
    return base if idx == 0 else f"{base} ({idx + 1})"


async def _add_papers(papers: list[dict]) -> tuple[int, list[str]]:
    try:
        from notebooklm import NotebookLMClient
        from notebooklm.exceptions import NotebookLMError, AuthError
    except ImportError:
        return 0, ["notebooklm-py 미설치: pip install 'notebooklm-py[browser]'"]

    chunks = [papers[i:i + NOTEBOOK_LIMIT] for i in range(0, len(papers), NOTEBOOK_LIMIT)]
    added = 0
    errors = []

    try:
        async with NotebookLMClient.from_storage() as client:
            for chunk_idx, chunk in enumerate(chunks):
                title = _notebook_title(NOTEBOOK_TITLE, chunk_idx)

                notebooks = await client.notebooks.list()
                notebook = next((nb for nb in notebooks if nb.title == title), None)
                if notebook is None:
                    notebook = await client.notebooks.create(title=title)
                    logger.info(f"NotebookLM 노트북 생성: {title}")
                else:
                    logger.info(f"NotebookLM 기존 노트북 사용: {title} (id={notebook.id})")

                for paper in chunk:
                    url = paper.get("link", "")
                    if not url:
                        continue
                    try:
                        await client.sources.add_url(
                            notebook_id=notebook.id,
                            url=url,
                            wait=False,
                        )
                        added += 1
                        logger.info(f"소스 추가: {paper['title'][:60]}")
                    except NotebookLMError as e:
                        errors.append(f"{paper['title'][:40]}: {e}")

    except AuthError:
        return 0, ["NotebookLM 인증 필요: 터미널에서 'notebooklm login' 실행 후 재시도"]
    except Exception as e:
        return 0, [f"NotebookLM 연결 실패: {e}"]

    return added, errors


def add_papers_to_notebooklm(papers: list[dict]) -> tuple[int, list[str]]:
    """동기 진입점 — main.py에서 직접 호출."""
    try:
        return asyncio.run(_add_papers(papers))
    except Exception as e:
        return 0, [str(e)]
