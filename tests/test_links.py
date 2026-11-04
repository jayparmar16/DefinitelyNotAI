"""Tests for python -m askwri.links: finding citation links between documents."""


def test_links_are_found_by_doi_url_or_title_and_never_point_forward_in_time():
    from askwri.links import find_links, normalize

    documents = [
        {
            "doc_id": "old",
            "title": "Tracking Adaptation Finance: An Approach",
            "doi": None,
            "url": "https://www.wri.org/research/tracking-adaptation-finance-approach",
            "year": 2012,
        },
        {
            "doc_id": "new",
            "title": "From Tracking to Action",
            "doi": "10.46830/wrirpt.15.1",
            "url": None,
            "year": 2015,
        },
    ]
    chunks = [
        {
            "chunk_id": "new#1",
            "doc_id": "new",
            "page": 9,
            "section": "Introduction",
            "content": "We build on Tracking Adaptation Finance (2012). It set out a method.",
        },
        {
            "chunk_id": "new#9",
            "doc_id": "new",
            "page": 60,
            "section": "References",
            "content": "WRI. 2012. Tracking adaptation finance: an approach. Washington, DC.",
        },
        {
            "chunk_id": "old#1",
            "doc_id": "old",
            "page": 3,
            "section": "",
            "content": "See From Tracking to Action, doi 10.46830/wrirpt.15.1.",
        },  # older can't cite newer
    ]
    for chunk in chunks:
        chunk["normalized"] = normalize(chunk["content"])
    links = find_links(documents, chunks)
    assert [(link.src, link.dst) for link in links] == [("new", "old")]
    link = links[0]
    # The mention in the text beats the reference entry, and keeps its sentence and page.
    assert (link.chunk_id, link.page, link.in_references) == ("new#1", 9, False)
    assert link.sentence == "We build on Tracking Adaptation Finance (2012)."
