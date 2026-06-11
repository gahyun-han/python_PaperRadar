"""
notebooklm_client.py — chunking / overflow 테스트
notebooklm 라이브러리는 mock으로 대체.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

# ── 테스트 픽스처 ────────────────────────────────────────────────────────────────

def _make_papers(n: int) -> list[dict]:
    return [{"title": f"Paper {i}", "link": f"https://arxiv.org/abs/2501.{i:05d}"} for i in range(n)]


def _make_notebooklm_mock(existing_titles: list[str] | None = None):
    """notebooklm 패키지를 통째로 mock 반환."""
    nb_mod = types.ModuleType("notebooklm")
    exc_mod = types.ModuleType("notebooklm.exceptions")

    class NotebookLMError(Exception):
        pass

    class AuthError(Exception):
        pass

    exc_mod.NotebookLMError = NotebookLMError
    exc_mod.AuthError = AuthError
    nb_mod.exceptions = exc_mod

    created_notebooks: list[MagicMock] = []
    existing = existing_titles or []

    def make_nb(title):
        nb = MagicMock()
        nb.title = title
        nb.id = f"nb-{len(created_notebooks)}"
        created_notebooks.append(nb)
        return nb

    # 기존 노트북 목록 (list() 반환용)
    pre_existing = [make_nb(t) for t in existing]

    mock_client = AsyncMock()
    mock_client.notebooks.list = AsyncMock(return_value=list(pre_existing))
    mock_client.notebooks.create = AsyncMock(side_effect=lambda title: make_nb(title))
    mock_client.sources.add_url = AsyncMock(return_value=None)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    class FakeClient:
        @staticmethod
        def from_storage():
            return ctx

    nb_mod.NotebookLMClient = FakeClient
    return nb_mod, exc_mod, mock_client, created_notebooks


# ── _notebook_title 유닛 테스트 ─────────────────────────────────────────────────

from notebooklm_client import _notebook_title, NOTEBOOK_TITLE


def test_notebook_title_first():
    assert _notebook_title("Base", 0) == "Base"


def test_notebook_title_second():
    assert _notebook_title("Base", 1) == "Base (2)"


def test_notebook_title_third():
    assert _notebook_title("Base", 2) == "Base (3)"


# ── _add_papers 통합 테스트 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_papers():
    from notebooklm_client import _add_papers
    nb_mod, exc_mod, mock_client, _ = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers([])
    assert added == 0
    assert errors == []
    mock_client.notebooks.create.assert_not_called()


@pytest.mark.asyncio
async def test_under_limit_single_notebook():
    from notebooklm_client import _add_papers
    papers = _make_papers(30)
    nb_mod, exc_mod, mock_client, created = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 30
    assert errors == []
    # 노트북 1개만 생성
    assert mock_client.notebooks.create.call_count == 1
    assert created[0].title == NOTEBOOK_TITLE


@pytest.mark.asyncio
async def test_exactly_limit_single_notebook():
    from notebooklm_client import _add_papers
    papers = _make_papers(50)
    nb_mod, exc_mod, mock_client, created = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 50
    assert mock_client.notebooks.create.call_count == 1


@pytest.mark.asyncio
async def test_51_papers_two_notebooks():
    from notebooklm_client import _add_papers
    papers = _make_papers(51)
    nb_mod, exc_mod, mock_client, created = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 51
    assert errors == []
    assert mock_client.notebooks.create.call_count == 2
    titles = [nb.title for nb in created]
    assert NOTEBOOK_TITLE in titles
    assert f"{NOTEBOOK_TITLE} (2)" in titles


@pytest.mark.asyncio
async def test_120_papers_three_notebooks():
    from notebooklm_client import _add_papers
    papers = _make_papers(120)
    nb_mod, exc_mod, mock_client, created = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 120
    assert mock_client.notebooks.create.call_count == 3
    titles = [nb.title for nb in created]
    assert NOTEBOOK_TITLE in titles
    assert f"{NOTEBOOK_TITLE} (2)" in titles
    assert f"{NOTEBOOK_TITLE} (3)" in titles


@pytest.mark.asyncio
async def test_paper_without_url_skipped():
    from notebooklm_client import _add_papers
    papers = [{"title": "No URL paper", "link": ""}, {"title": "Has URL", "link": "https://arxiv.org/abs/2501.00001"}]
    nb_mod, exc_mod, mock_client, _ = _make_notebooklm_mock()
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 1
    assert errors == []


@pytest.mark.asyncio
async def test_existing_notebook_reused():
    from notebooklm_client import _add_papers
    papers = _make_papers(10)
    nb_mod, exc_mod, mock_client, _ = _make_notebooklm_mock(existing_titles=[NOTEBOOK_TITLE])
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 10
    # 기존 노트북 재사용 → create 호출 없음
    mock_client.notebooks.create.assert_not_called()


@pytest.mark.asyncio
async def test_notebooklm_error_goes_to_errors():
    from notebooklm_client import _add_papers
    papers = _make_papers(2)
    nb_mod, exc_mod, mock_client, _ = _make_notebooklm_mock()
    # 두 번째 논문 추가 시 에러 발생
    call_count = {"n": 0}

    async def add_url_side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise exc_mod.NotebookLMError("duplicate source")

    mock_client.sources.add_url.side_effect = add_url_side_effect
    with patch.dict(sys.modules, {"notebooklm": nb_mod, "notebooklm.exceptions": exc_mod}):
        added, errors = await _add_papers(papers)
    assert added == 1
    assert len(errors) == 1
    assert "duplicate source" in errors[0]
