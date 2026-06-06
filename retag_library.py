"""
Zotero 라이브러리 전체 재태깅 + 컬렉션 동기화.
- 기존 태그는 유지, atomic 태그(domain:X / method:X / problem:X)만 추가
- 재태깅 완료 후 Domain/Method/Problem 계층 컬렉션 자동 생성 및 할당
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pyzotero import zotero as pyzotero
from tagger import tag_paper

ZOTERO_USER_ID = "20683965"
ZOTERO_API_KEY = "v5ATjSK5LAYMNuZ2CdkmUQVr"
LOG_FILE = Path(__file__).parent / "retag_progress.log"
JARVIS_PATH = "/Users/hanga/Desktop/claude/Jarvis"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    LOG_FILE.write_text("", encoding="utf-8")
    log("=== Zotero 재태깅 시작 ===\n")

    zot = pyzotero.Zotero(ZOTERO_USER_ID, "user", ZOTERO_API_KEY)

    # ── 1. 전체 아이템 로드 ────────────────────────────────────────────────
    log("라이브러리 로딩 중 (시간 걸릴 수 있음)...")
    all_items = [
        i for i in zot.everything(zot.top())
        if i.get("data", {}).get("itemType") != "attachment"
    ]
    log(f"총 {len(all_items)}편 로드 완료\n")

    # ── 2. 재태깅 ─────────────────────────────────────────────────────────
    updated_count = 0
    skipped_count = 0
    tag_stats: dict[str, int] = {}  # 태그별 추가 횟수

    for idx, item in enumerate(all_items, 1):
        data = item["data"]
        paper = {
            "title": data.get("title", ""),
            "summary": data.get("abstractNote", ""),
            "keywords": [],
        }

        new_tags = tag_paper(paper)
        existing = {t["tag"] for t in data.get("tags", [])}
        to_add = [t for t in new_tags if t not in existing]

        if not to_add:
            skipped_count += 1
        else:
            item["data"]["tags"] = data.get("tags", []) + [{"tag": t} for t in to_add]
            try:
                zot.update_item(item)
                updated_count += 1
                for t in to_add:
                    tag_stats[t] = tag_stats.get(t, 0) + 1
                log(f"  [{idx:3d}/{len(all_items)}] +{len(to_add)}tags  {data['title'][:55]}")
            except Exception as e:
                log(f"  [{idx:3d}] ⚠️  오류: {e}")
            time.sleep(0.4)  # Zotero API rate limit 방지

        # 50편마다 중간 집계 + 짧은 휴식
        if idx % 50 == 0:
            log(f"\n  ── 중간 집계 [{idx}/{len(all_items)}] 업데이트:{updated_count} 스킵:{skipped_count} ──\n")
            time.sleep(3)

    log(f"\n=== 재태깅 완료: {updated_count}편 업데이트 / {skipped_count}편 스킵 ===")

    # 태그별 통계
    if tag_stats:
        log("\n태그별 추가 횟수:")
        for tag, cnt in sorted(tag_stats.items(), key=lambda x: -x[1]):
            log(f"  {tag}: {cnt}편")

    # ── 3. 컬렉션 동기화 (Domain/Method/Problem 계층 생성) ────────────────
    log("\n\n=== 컬렉션 동기화 시작 (Domain/Method/Problem 계층 생성) ===")
    try:
        if JARVIS_PATH not in sys.path:
            sys.path.insert(0, JARVIS_PATH)
        import os
        os.environ.setdefault("ZOTERO_API_KEY", ZOTERO_API_KEY)
        os.environ.setdefault("ZOTERO_USER_ID", ZOTERO_USER_ID)

        from dotenv import load_dotenv
        load_dotenv(Path(JARVIS_PATH) / ".env")

        from agents.paper.zotero_client import ZoteroClient
        client = ZoteroClient()
        result = client.sync_collections_from_tags()
        log(result)
    except Exception as e:
        log(f"⚠️  컬렉션 동기화 오류: {e}")

    log("\n=== 모든 작업 완료 ===")


if __name__ == "__main__":
    main()
