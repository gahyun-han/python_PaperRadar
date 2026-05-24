import arxiv


def fetch_arxiv_papers():
    client = arxiv.Client()

    search = arxiv.Search(
        query="cat:cs.AI",
        max_results=30,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    papers = []

    for result in client.results(search):
        paper = {
            "title": result.title,
            "summary": result.summary,
            "link": result.entry_id
        }

        papers.append(paper)

    return papers