import re
import arxiv


def _stable_id(entry_id: str) -> str:
    """버전 번호 제거 — 2605.30283v1 → 2605.30283 (v2가 와도 같은 키)"""
    return re.sub(r"v\d+$", "", entry_id.split("/abs/")[-1])


def fetch_arxiv_papers():
    client = arxiv.Client()

    search = arxiv.Search(
        query="cat:cs.AI",
        max_results=60,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    papers = []

    for result in client.results(search):
        paper = {
            "title": result.title,
            "summary": result.summary,
            "link": result.entry_id,
            "arxiv_id": _stable_id(result.entry_id),
            "authors": [a.name for a in result.authors],
            "published": result.published.strftime("%Y-%m-%d") if result.published else "",
        }

        papers.append(paper)

    return papers