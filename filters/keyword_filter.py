from config import KEYWORDS


def score_paper(paper):
    text = (
        paper["title"] + " " + paper["summary"]
    ).lower()

    score = 0

    matched_keywords = []

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 1
            matched_keywords.append(keyword)

    return score, matched_keywords


def filter_papers(papers, threshold=2):
    selected = []

    for paper in papers:
        score, keywords = score_paper(paper)

        if score >= threshold:
            paper["score"] = score
            paper["keywords"] = keywords

            selected.append(paper)

    return selected