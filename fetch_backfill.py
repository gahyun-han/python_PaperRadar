"""
종합 백필 — 2025-01 ~ 2026-06 전체 기간, 20개 조합 쿼리로 최대한 많은 논문 수집.
429 발생 시 대기 후 재시도. 쿼리별로 즉시 Zotero 저장 (중간 실패해도 진행분 유지).
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import arxiv

from zotero_client import ZoteroClient
from tagger import tag_paper

HISTORY_FILE = Path(__file__).parent / "sent_history.json"
LOG_FILE     = Path(__file__).parent / "backfill_progress.log"

DATE_FROM = "202501010000"
DATE_TO   = "202606302359"
PY_FROM   = datetime(2025, 1, 1)
PY_TO     = datetime(2026, 6, 30)

# ── 20개 조합 쿼리 ─────────────────────────────────────────────────────────────
# (label, arxiv_query_template, scoring_keywords)
QUERIES = [
    # ── Digital Twin 조합 ──
    ("DT + Multi-Agent",
     'ti:"digital twin" AND (ti:"multi-agent" OR abs:"multi-agent system")',
     ["digital twin", "multi-agent"]),

    ("DT + Knowledge Graph",
     '(ti:"digital twin" OR abs:"digital twin") AND (ti:"knowledge graph" OR abs:"knowledge graph")',
     ["digital twin", "knowledge graph"]),

    ("DT + Agentic AI",
     '(ti:"digital twin" OR abs:"digital twin") AND (abs:"agentic ai" OR abs:"agentic workflow" OR ti:"agentic")',
     ["digital twin", "agentic ai"]),

    ("DT + Reinforcement Learning",
     'ti:"digital twin" AND (ti:"reinforcement learning" OR abs:"reinforcement learning")',
     ["digital twin", "reinforcement learning"]),

    ("DT + Scheduling",
     'ti:"digital twin" AND (abs:"scheduling" OR abs:"resource allocation")',
     ["digital twin", "scheduling"]),

    ("DT + RAG",
     'ti:"digital twin" AND (abs:"retrieval" OR abs:"rag" OR abs:"retrieval-augmented")',
     ["digital twin", "rag"]),

    ("DT + Ontology",
     '(ti:"digital twin" OR abs:"digital twin") AND (ti:"ontology" OR abs:"ontology")',
     ["digital twin", "ontology"]),

    ("DT + LLM",
     'ti:"digital twin" AND (abs:"large language model" OR abs:"llm" OR ti:"llm")',
     ["digital twin", "llm"]),

    ("DT + Simulation",
     'ti:"digital twin" AND abs:"simulation" AND cat:cs.AI',
     ["digital twin", "simulation"]),

    # ── Multi-Agent 조합 ──
    ("Multi-Agent + Simulation",
     'cat:cs.AI AND ti:"multi-agent" AND (ti:"simulation" OR abs:"simulation framework")',
     ["multi-agent", "simulation"]),

    ("Multi-Agent + Scheduling",
     'cat:cs.AI AND ti:"multi-agent" AND (abs:"scheduling" OR abs:"task allocation")',
     ["multi-agent", "scheduling"]),

    ("Multi-Agent + Knowledge Graph",
     'cat:cs.AI AND ti:"multi-agent" AND (abs:"knowledge graph" OR abs:"knowledge base")',
     ["multi-agent", "knowledge graph"]),

    ("Multi-Agent + Ontology",
     'cat:cs.AI AND ti:"multi-agent" AND (ti:"ontology" OR abs:"ontology-based")',
     ["multi-agent", "ontology"]),

    ("Multi-Agent + RAG",
     'cat:cs.AI AND ti:"multi-agent" AND (abs:"retrieval-augmented" OR abs:"rag" OR ti:"rag")',
     ["multi-agent", "rag"]),

    # ── Industrial / Physical AI ──
    ("Industrial AI",
     'cat:cs.AI AND (ti:"industrial ai" OR ti:"factory ai" OR abs:"industrial artificial intelligence")',
     ["industrial ai", "factory ai"]),

    ("Physical AI",
     'cat:cs.AI AND (ti:"physical ai" OR abs:"physical ai" OR abs:"cyber-physical" OR ti:"cyber-physical")',
     ["physical ai", "simulation"]),

    # ── Agentic AI 단독 ──
    ("Agentic AI + Simulation",
     'cat:cs.AI AND (ti:"agentic ai" OR abs:"agentic ai") AND abs:"simulation"',
     ["agentic ai", "simulation"]),

    ("Agentic AI + RAG",
     'cat:cs.AI AND (ti:"agentic" OR abs:"agentic ai") AND (abs:"retrieval-augmented" OR abs:"rag")',
     ["agentic ai", "rag"]),

    # ── Ontology / Knowledge Graph ──
    ("Ontology + RAG",
     'cat:cs.AI AND (ti:"ontology" OR abs:"ontology-based") AND (abs:"retrieval-augmented" OR abs:"rag")',
     ["ontology", "rag"]),

    ("Knowledge Graph + RAG",
     'cat:cs.AI AND (ti:"knowledge graph" OR abs:"knowledge graph") AND (abs:"retrieval-augmented" OR abs:"rag" OR ti:"rag")',
     ["knowledge graph", "rag"]),
]

PER_QUERY = 60   # 쿼리당 최대 수집 수


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


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


def score_paper(paper: dict, keywords: list[str]) -> int:
    text = (paper.get("title", "") + " " + paper.get("summary", "")).lower()
    return sum(1 for kw in keywords if kw.lower() in text)


def fetch_query(query: str, max_results: int) -> tuple[list[dict], bool]:
    """논문 수집. (papers, rate_limited) 반환."""
    full_q = f"({query}) AND submittedDate:[{DATE_FROM} TO {DATE_TO}]"
    client = arxiv.Client(page_size=10, delay_seconds=12, num_retries=2)
    search = arxiv.Search(query=full_q, max_results=max_results,
                          sort_by=arxiv.SortCriterion.SubmittedDate)
    papers = []
    rate_limited = False
    try:
        for result in client.results(search):
            pub = result.published.strftime("%Y-%m-%d") if result.published else ""
            if pub and not (PY_FROM <= datetime.strptime(pub, "%Y-%m-%d") <= PY_TO):
                continue
            papers.append({
                "title":    result.title,
                "summary":  result.summary,
                "link":     result.entry_id,
                "arxiv_id": re.sub(r"v\d+$", "", result.entry_id.split("/abs/")[-1]),
                "authors":  [a.name for a in result.authors],
                "published": pub,
            })
    except Exception as e:
        if "429" in str(e) or "503" in str(e):
            rate_limited = True
        log(f"  ⚠️  수집 중단: {e}")
    return papers, rate_limited


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    LOG_FILE.write_text("", encoding="utf-8")   # 로그 초기화
    log(f"=== 종합 백필 시작: {DATE_FROM[:8]} ~ {DATE_TO[:8]} ({len(QUERIES)}개 쿼리) ===\n")

    sent_ids = load_sent_ids()
    zot = ZoteroClient()
    grand_total = 0

    for qi, (label, query, keywords) in enumerate(QUERIES, 1):
        # 쿼리 간 대기 (첫 번째는 짧게)
        wait = 15 if qi == 1 else 35
        log(f"[{qi}/{len(QUERIES)}] {label} — {wait}초 대기...")
        time.sleep(wait)

        papers, rate_limited = fetch_query(query, PER_QUERY)

        # 429 → 더 길게 대기 후 1회 재시도
        if rate_limited:
            log(f"  레이트 리밋 → 90초 대기 후 재시도...")
            time.sleep(90)
            papers, rate_limited = fetch_query(query, PER_QUERY)
            if rate_limited:
                log(f"  재시도 실패 — 건너뜀")
                continue

        # 중복 + 스코어 필터 + 원자적 태깅
        new_papers = []
        for p in papers:
            aid = p["arxiv_id"]
            if not aid or aid in sent_ids:
                continue
            score = score_paper(p, keywords)
            if score >= 1:
                p["score"]    = score
                p["keywords"] = [kw for kw in keywords if kw.lower() in (p["title"] + p["summary"]).lower()]
                p["tags"]     = tag_paper(p)
                new_papers.append(p)

        log(f"  수집 {len(papers)}편 → 신규 {len(new_papers)}편")

        if not new_papers:
            continue

        # Zotero 즉시 저장 (쿼리별로 저장해 중간 실패 대비)
        added, errors = zot.add_papers(new_papers)
        log(f"  Zotero +{added}편" + (f" (오류 {len(errors)}건)" if errors else ""))
        sent_ids.update(p["arxiv_id"] for p in new_papers)
        save_sent_ids(sent_ids)
        grand_total += added

        # Zotero API 과부하 방지
        time.sleep(3)

    log(f"\n=== 수집 완료: 총 {grand_total}편 Zotero 저장 ===")

    # 컬렉션 동기화
    log("\n컬렉션 동기화 중...")
    try:
        JARVIS = "/Users/hanga/Desktop/claude/Jarvis"
        if JARVIS not in sys.path:
            sys.path.insert(0, JARVIS)
        os.environ.setdefault("ZOTERO_API_KEY", "v5ATjSK5LAYMNuZ2CdkmUQVr")
        os.environ.setdefault("ZOTERO_USER_ID", "20683965")
        from agents.paper.zotero_client import ZoteroClient
        from agents.paper.landscape_builder import build_landscape, save_landscape
        client = ZoteroClient()
        sync_result = client.sync_collections_from_tags()
        log(sync_result)
        data = build_landscape(client.zot)
        save_landscape(data)
        log(f"📊 Landscape 갱신 완료: {data['total_papers']}편")
    except Exception as e:
        log(f"⚠️  후처리 오류: {e}")

    log("\n=== 모든 작업 완료 ===")


if __name__ == "__main__":
    main()
