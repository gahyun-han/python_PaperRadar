"""
일회성: manufacturing + knowledge graph 논문 수집 → Zotero → NotebookLM
기간: 2025-12-01 ~ 2026-06-11 (최근 6개월)
"""
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import arxiv

sys.path.insert(0, str(Path(__file__).parent))

from zotero_client import ZoteroClient
from tagger import tag_paper

HISTORY_FILE = Path(__file__).parent / "sent_history.json"
DATE_FROM = "202512010000"
DATE_TO   = "202606112359"
PY_FROM   = datetime(2025, 12, 1)
PY_TO     = datetime(2026, 6, 11)

QUERIES = [
    ("Manufacturing + Knowledge Graph (title)",
     '(ti:"manufacturing" OR ti:"smart factory" OR ti:"industry 4.0" OR ti:"industrial") AND (ti:"knowledge graph" OR abs:"knowledge graph")',
     ["manufacturing", "knowledge graph"]),

    ("Manufacturing + Knowledge Graph (abstract)",
     '(abs:"manufacturing" OR abs:"smart factory" OR abs:"shop floor") AND ti:"knowledge graph"',
     ["manufacturing", "knowledge graph"]),

    ("Manufacturing + KG + LLM",
     '(ti:"manufacturing" OR abs:"manufacturing" OR abs:"industrial") AND (abs:"knowledge graph") AND (abs:"large language model" OR abs:"llm")',
     ["manufacturing", "knowledge graph", "llm"]),

    ("Manufacturing + KG + Digital Twin",
     '(ti:"manufacturing" OR abs:"manufacturing") AND (abs:"knowledge graph") AND (abs:"digital twin")',
     ["manufacturing", "knowledge graph", "digital twin"]),
]

PER_QUERY = 100


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_sent_ids() -> set:
    if HISTORY_FILE.exists():
        try:
            return set(json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_sent_ids(sent_ids: set):
    HISTORY_FILE.write_text(
        json.dumps(sorted(sent_ids), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_query(query: str, max_results: int) -> tuple[list[dict], bool]:
    full_q = f"({query}) AND submittedDate:[{DATE_FROM} TO {DATE_TO}]"
    client = arxiv.Client(page_size=10, delay_seconds=12, num_retries=3)
    search = arxiv.Search(query=full_q, max_results=max_results,
                          sort_by=arxiv.SortCriterion.SubmittedDate)
    papers = []
    rate_limited = False
    try:
        for result in client.results(search):
            pub = result.published.strftime("%Y-%m-%d") if result.published else ""
            if pub:
                pub_dt = datetime.strptime(pub, "%Y-%m-%d")
                if not (PY_FROM <= pub_dt <= PY_TO):
                    continue
            papers.append({
                "title":     result.title,
                "summary":   result.summary,
                "link":      result.entry_id,
                "arxiv_id":  re.sub(r"v\d+$", "", result.entry_id.split("/abs/")[-1]),
                "authors":   [a.name for a in result.authors],
                "published": pub,
            })
    except Exception as e:
        if "429" in str(e) or "503" in str(e):
            rate_limited = True
        log(f"  ⚠️  수집 중단: {e}")
    return papers, rate_limited


async def upload_notebooklm(papers: list[dict], notebook_title: str) -> tuple[int, list[str]]:
    try:
        from notebooklm import NotebookLMClient
        from notebooklm.exceptions import NotebookLMError, AuthError
    except ImportError:
        return 0, ["notebooklm-py 미설치: pip install 'notebooklm-py[browser]'"]

    added = 0
    errors = []
    try:
        async with NotebookLMClient.from_storage() as client:
            notebooks = await client.notebooks.list()
            notebook = next((nb for nb in notebooks if nb.title == notebook_title), None)
            if notebook is None:
                notebook = await client.notebooks.create(title=notebook_title)
                log(f"  노트북 생성: '{notebook_title}'")
            else:
                log(f"  기존 노트북 사용: '{notebook_title}' (id={notebook.id})")

            for paper in papers:
                url = paper.get("link", "")
                if not url:
                    continue
                try:
                    await client.sources.add_url(notebook_id=notebook.id, url=url, wait=False)
                    added += 1
                except NotebookLMError as e:
                    errors.append(f"{paper['title'][:40]}: {e}")
    except AuthError:
        return 0, ["NotebookLM 인증 필요: 터미널에서 'notebooklm login' 실행 후 재시도"]
    except Exception as e:
        return 0, [f"NotebookLM 연결 실패: {e}"]
    return added, errors


def main():
    log(f"=== manufacturing + knowledge graph 논문 수집 시작 ({DATE_FROM[:8]} ~ {DATE_TO[:8]}) ===\n")

    sent_ids = load_sent_ids()
    log(f"기존 sent_history: {len(sent_ids)}편\n")

    zot = ZoteroClient()
    all_new_papers: list[dict] = []
    seen_this_run: set[str] = set()

    for qi, (label, query, keywords) in enumerate(QUERIES, 1):
        wait = 10 if qi == 1 else 30
        log(f"[{qi}/{len(QUERIES)}] {label} — {wait}초 대기...")
        time.sleep(wait)

        papers, rate_limited = fetch_query(query, PER_QUERY)
        if rate_limited:
            log("  레이트 리밋 → 90초 대기 후 재시도...")
            time.sleep(90)
            papers, rate_limited = fetch_query(query, PER_QUERY)
            if rate_limited:
                log("  재시도 실패 — 건너뜀")
                continue

        new_papers = []
        for p in papers:
            aid = p["arxiv_id"]
            if not aid or aid in sent_ids or aid in seen_this_run:
                continue
            p["score"]    = sum(1 for kw in keywords if kw.lower() in (p["title"] + p["summary"]).lower())
            p["keywords"] = keywords
            p["tags"]     = tag_paper(p)
            new_papers.append(p)
            seen_this_run.add(aid)

        log(f"  수집 {len(papers)}편 → 신규 {len(new_papers)}편")
        if not new_papers:
            continue

        added, errors, _ = zot.add_papers(new_papers)
        log(f"  Zotero +{added}편" + (f" (오류 {len(errors)}건: {errors[:2]})" if errors else ""))
        sent_ids.update(p["arxiv_id"] for p in new_papers)
        save_sent_ids(sent_ids)
        all_new_papers.extend(new_papers)
        time.sleep(3)

    log(f"\n=== 수집 완료: 총 {len(all_new_papers)}편 ===\n")

    if not all_new_papers:
        log("업로드할 논문이 없습니다.")
        return

    # NotebookLM 업로드 (50개 제한 → 넘으면 추가 노트북)
    LIMIT = 50
    base_title = "PaperRadar — Manufacturing × KG"
    chunks = [all_new_papers[i:i + LIMIT] for i in range(0, len(all_new_papers), LIMIT)]
    log(f"NotebookLM 업로드: {len(all_new_papers)}편 → {len(chunks)}개 노트북\n")

    total_uploaded = 0
    for idx, chunk in enumerate(chunks, 1):
        nb_title = base_title if idx == 1 else f"{base_title} ({idx})"
        log(f"노트북 '{nb_title}' — {len(chunk)}편 업로드 중...")
        added_nb, errs_nb = asyncio.run(upload_notebooklm(chunk, nb_title))
        log(f"  → {added_nb}편 업로드 완료" + (f", 오류 {len(errs_nb)}건" if errs_nb else ""))
        for e in errs_nb[:3]:
            log(f"    {e}")
        total_uploaded += added_nb

    log(f"\n=== NotebookLM 업로드 완료: 총 {total_uploaded}편 ===")


if __name__ == "__main__":
    main()
