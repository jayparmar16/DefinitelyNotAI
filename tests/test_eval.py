from eval.run_eval import figures_cited


def test_figures_cited_reads_sentences_as_the_agent_writes_them():
    cited = ["Studies (Smith et al. 2011; Lee et al. 2017) show losses fall 42 percent [1]."]
    assert figures_cited(cited) == 1.0
    assert figures_cited(["Losses fell 42 percent. It worked [1]."]) == 0.0
    assert figures_cited(["No figures here [1]."]) is None
