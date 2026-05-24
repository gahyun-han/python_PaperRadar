from collectors.arxiv_collector import fetch_arxiv_papers
from filters.keyword_filter import filter_papers

from telegram_utils.sender import send_telegram_message

from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID
)

papers = fetch_arxiv_papers()
print(f"수집 논문 수: {len(papers)}")
for paper in papers[:5]:
    print(paper["title"])

selected = filter_papers(papers)
print(f"필터 통과 논문 수: {len(selected)}")

message = "📄 AI/DT 논문 브리핑\n\n"

for idx, paper in enumerate(selected[:5], start=1):
    message += (
        f"{idx}. {paper['title']}\n"
        f"⭐ score: {paper['score']}\n"
        f"🏷 {', '.join(paper['keywords'])}\n"
        f"{paper['link']}\n\n"
    )
print(message)

send_telegram_message(
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    message
)
