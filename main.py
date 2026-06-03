import json
from datetime import datetime, timezone
from pathlib import Path

from collectors.arxiv_collector import fetch_arxiv_papers
from filters.keyword_filter import filter_papers
from telegram_utils.sender import send_telegram_message
from zotero_client import ZoteroClient
from tagger import tag_paper
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

HISTORY_FILE = Path(__file__).parent / "sent_history.json"
JARVIS_LOG = Path("/Users/hanga/Desktop/claude/Jarvis/data/execution_log.json")


JARVIS_PATH = Path("/Users/hanga/Desktop/claude/Jarvis")


def _update_landscape():
    """Jarvis landscape_builder 를 호출해 summary.json 을 갱신한다."""
    try:
        import sys
        if str(JARVIS_PATH) not in sys.path:
            sys.path.insert(0, str(JARVIS_PATH))
        from dotenv import load_dotenv as _load
        _load(JARVIS_PATH / ".env")
        from agents.paper.landscape_builder import build_landscape, save_landscape
        from agents.paper.zotero_obsidian_client import ZoteroObsidianClient
        client = ZoteroObsidianClient()
        if client.zot:
            data = build_landscape(client.zot)
            path = save_landscape(data)
            print(f"📊 Landscape 갱신 완료: {data['total_papers']}편 → {path}")
    except Exception as e:
        print(f"⚠️  Landscape 갱신 실패: {e}")


def log_to_jarvis(success: bool, papers_sent: int, zotero_added: int, errors: list):
    """Jarvis execution_log에 직접 실행 결과를 기록한다. subprocess 불필요."""
    try:
        log = json.loads(JARVIS_LOG.read_text(encoding="utf-8")) if JARVIS_LOG.exists() else []
        log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": "PaperRadar",
            "event": "run",
            "success": success,
            "papers_sent": papers_sent,
            "zotero_added": zotero_added,
            "errors": errors,
        })
        JARVIS_LOG.write_text(json.dumps(log[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️  Jarvis 로그 기록 실패: {e}")


def load_sent_ids() -> set:
    """영구 저장된 발송 완료 arxiv_id 집합 반환."""
    if HISTORY_FILE.exists():
        try:
            return set(json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_sent_ids(sent_ids: set):
    HISTORY_FILE.write_text(json.dumps(sorted(sent_ids), ensure_ascii=False, indent=2), encoding="utf-8")


def filter_new_papers(papers: list, sent_ids: set) -> list:
    """이미 보낸 arxiv_id를 가진 논문 제거."""
    new_papers = []
    for paper in papers:
        if paper["arxiv_id"] in sent_ids:
            print(f"⏭️  중복 건너뜀: {paper['title'][:50]}...")
        else:
            new_papers.append(paper)
    return new_papers


papers = fetch_arxiv_papers()
print(f"수집 논문 수: {len(papers)}")

selected = filter_papers(papers)
print(f"필터 통과 논문 수: {len(selected)}")

# 원자적 태그 부여
for p in selected:
    p["tags"] = tag_paper(p)

sent_ids = load_sent_ids()
new_selected = filter_new_papers(selected, sent_ids)
print(f"신규 논문 수 (중복 제외): {len(new_selected)}")

if not new_selected:
    print("✅ 새로운 논문이 없습니다.")
    send_telegram_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, "📄 오늘은 새로운 논문이 없습니다.")
    log_to_jarvis(success=True, papers_sent=0, zotero_added=0, errors=[])
    _update_landscape()
else:
    to_send = new_selected[:5]
    message = "📄 AI/DT 논문 브리핑\n\n"
    for idx, paper in enumerate(to_send, start=1):
        # 태그를 group별로 묶어 포맷
        groups: dict[str, list[str]] = {}
        for tag in paper.get("tags", []):
            if ":" in tag:
                grp, val = tag.split(":", 1)
                groups.setdefault(grp, []).append(val)
        if groups:
            tag_lines = "\n".join(f"🏷 {grp} : {', '.join(vals)}" for grp, vals in groups.items())
        else:
            tag_lines = "🏷 —"
        message += (
            f"{idx}. {paper['title']}\n"
            f"⭐ score: {paper['score']}\n"
            f"{tag_lines}\n"
            f"{paper['link']}\n\n"
        )
    print(message)
    send_telegram_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message)

    sent_ids.update(p["arxiv_id"] for p in to_send)
    save_sent_ids(sent_ids)
    print(f"🚀 발송 완료. 히스토리 {len(sent_ids)}편 저장.")

    # 태그 결과 JSON 저장
    tagged_log_path = Path(__file__).parent / "outputs" / "tagged_papers.json"
    tagged_log_path.parent.mkdir(exist_ok=True)
    existing: list = []
    if tagged_log_path.exists():
        try:
            existing = json.loads(tagged_log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    for p in to_send:
        existing.append({
            "arxiv_id": p["arxiv_id"],
            "title": p["title"],
            "published": p.get("published", ""),
            "tags": p.get("tags", []),
            "score": p.get("score", 0),
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })
    tagged_log_path.write_text(json.dumps(existing[-5000:], ensure_ascii=False, indent=2), encoding="utf-8")

    # Zotero에 자동 추가
    zot = ZoteroClient()
    added, errors = zot.add_papers(to_send)
    if added:
        print(f"📚 Zotero에 {added}편 추가 완료.")
    if errors:
        print(f"⚠️  Zotero 오류: {errors}")

    # NotebookLM에 소스 추가
    from notebooklm_client import add_papers_to_notebooklm
    nlm_added, nlm_errors = add_papers_to_notebooklm(to_send)
    if nlm_added:
        print(f"📓 NotebookLM에 {nlm_added}편 소스 추가 완료.")
    if nlm_errors:
        print(f"⚠️  NotebookLM 오류: {nlm_errors}")

    # Jarvis execution_log에 결과 기록 (cross-project 직접 파일 쓰기)
    log_to_jarvis(success=True, papers_sent=len(to_send), zotero_added=added, errors=errors + nlm_errors)

    # Landscape 갱신
    _update_landscape()
