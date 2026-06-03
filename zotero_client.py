"""
Zotero client for PaperRadar.
Adds sent arxiv papers to the Zotero library via the web API (pyzotero).
Also downloads the PDF and attaches it as a linked_file so the paper
can be read and annotated directly in Zotero — no internet needed after download.

Zotero desktop does NOT need to be open for metadata+attachment creation.
PDFs are saved to ~/Documents/Papers/{arxiv_id}.pdf.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from pyzotero import zotero as pyzotero
    _PYZOTERO_OK = True
except ImportError:
    _PYZOTERO_OK = False

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

logger = logging.getLogger(__name__)

ZOTERO_USER_ID = "20683965"
ZOTERO_API_KEY = "v5ATjSK5LAYMNuZ2CdkmUQVr"
PDF_DIR = Path.home() / "Documents" / "Papers"
_ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"


def _build_item(paper: dict) -> dict:
    creators = []
    for name in paper.get("authors", []):
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            creators.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]})
        else:
            creators.append({"creatorType": "author", "name": name})

    arxiv_id = paper.get("arxiv_id", "")
    link = paper.get("link", "")
    if arxiv_id and "arxiv.org" not in link:
        link = f"https://arxiv.org/abs/{arxiv_id}"

    return {
        "itemType": "preprint",
        "title": paper.get("title", ""),
        "creators": creators,
        "abstractNote": paper.get("summary", "")[:2000],
        "repository": "arXiv",
        "archiveID": f"arXiv:{arxiv_id}" if arxiv_id else "",
        "date": paper.get("published", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "url": link,
        "accessDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tags": [{"tag": t} for t in paper.get("tags", [])],
        "collections": [],
        "relations": {},
    }


def _download_pdf(arxiv_id: str) -> Path | None:
    """Download arxiv PDF to ~/Documents/Papers/. Returns path or None on failure."""
    if not _REQUESTS_OK:
        return None
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_DIR / f"{arxiv_id}.pdf"
    if dest.exists():
        return dest  # 이미 있으면 재사용
    try:
        resp = _requests.get(
            _ARXIV_PDF.format(arxiv_id=arxiv_id),
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info(f"PDF saved: {dest} ({len(resp.content):,} bytes)")
        return dest
    except Exception as e:
        logger.warning(f"PDF download failed for {arxiv_id}: {e}")
        return None


def _attach_pdf(zot, item_key: str, pdf_path: Path, title: str):
    """Create a linked_file attachment child item in Zotero."""
    attachment = {
        "itemType": "attachment",
        "parentItem": item_key,
        "linkMode": "linked_file",
        "title": f"{title[:60]}.pdf",
        "path": str(pdf_path),
        "contentType": "application/pdf",
        "tags": [],
        "relations": {},
    }
    result = zot.create_items([attachment])
    return bool(result.get("successful"))


class ZoteroClient:
    def __init__(self):
        if not _PYZOTERO_OK:
            logger.warning("pyzotero not installed — Zotero sync disabled")
            self._zot = None
            return
        try:
            self._zot = pyzotero.Zotero(ZOTERO_USER_ID, "user", ZOTERO_API_KEY)
        except Exception as e:
            logger.error(f"Zotero init error: {e}")
            self._zot = None

    def add_papers(self, papers: list[dict]) -> tuple[int, list[str]]:
        """
        Add papers to Zotero library with PDF attachments.
        Returns (added_count, error_messages).
        """
        if not self._zot or not papers:
            return 0, []

        errors = []
        added = 0

        for paper in papers:
            arxiv_id = paper.get("arxiv_id", "")
            title = paper.get("title", arxiv_id)
            try:
                # 1) 메타데이터 항목 생성
                result = self._zot.create_items([_build_item(paper)])
                successful = result.get("successful", {})
                if not successful:
                    for fail in result.get("failed", {}).values():
                        errors.append(fail.get("message", "unknown"))
                    continue
                item_key = list(successful.values())[0]["key"]
                added += 1

                # 2) PDF 다운로드 → linked_file 첨부
                pdf_path = _download_pdf(arxiv_id)
                if pdf_path:
                    _attach_pdf(self._zot, item_key, pdf_path, title)
                    logger.info(f"Attached PDF to {item_key}: {arxiv_id}")
                else:
                    logger.warning(f"Skipped PDF attachment for {arxiv_id}")

            except Exception as e:
                logger.error(f"Zotero add error for {arxiv_id}: {e}")
                errors.append(str(e))

        return added, errors


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
