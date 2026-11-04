"""Sorting the corpus, driven through small synthetic PDFs built in the tests."""

import shutil
from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.sort import DUPLICATE, NOT_ENGLISH, OLDER_VERSION, sort_corpus

ENGLISH = (
    "The report describes how the forests of the region are managed and why the results "
    "matter for the people that live there. It is based on data from the national surveys "
    "and has been reviewed by experts in the field. "
)
SPANISH = (
    "El informe describe cómo se gestionan los bosques de la región y por qué los resultados "
    "son importantes para las personas que viven allí. Se basa en los datos de las encuestas "
    "nacionales y ha sido revisado por expertos en la materia. "
)
FRENCH = (
    "Le rapport décrit comment les forêts de la région sont gérées et pourquoi les résultats "
    "sont importants pour les personnes qui y vivent. Il est basé sur les données des "
    "enquêtes nationales et a été examiné par des experts dans le domaine. "
)
CHINESE = "该报告描述了该地区森林的管理方式以及结果对当地居民的重要性。报告基于国家调查的数据。" * 4


def make_pdf(folder: Path, name: str, body: str = ENGLISH, cover: str = "") -> Path:
    """Write a one-page PDF whose text is `cover` then `body`; different texts, different bytes."""
    folder.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    font = "china-s" if body == CHINESE else "helv"
    page.insert_textbox(
        pymupdf.Rect(50, 50, 550, 750), f"{cover}\n{body}", fontsize=10, fontname=font
    )
    path = folder / name
    doc.save(path)
    return path


def names(documents) -> set[str]:
    return {document.path.name for document in documents}


def reasons(corpus) -> dict[str, str]:
    return {dropped.path.name: dropped.reason for dropped in corpus.dropped}


def test_exact_duplicates_keep_one_file_and_name_it_in_the_reason(tmp_path):
    original = make_pdf(tmp_path, "forest-report.pdf")
    reupload = tmp_path / "forest-report_0.pdf"
    renamed = tmp_path / "forest-report-with-a-longer-name.pdf"
    shutil.copy(original, reupload)
    shutil.copy(original, renamed)

    corpus = sort_corpus([reupload, renamed, original])

    assert [d.path for d in corpus.kept] == [original]
    assert reasons(corpus) == {reupload.name: DUPLICATE, renamed.name: DUPLICATE}
    assert all(original.name in d.detail for d in corpus.dropped)


def test_version_family_keeps_the_latest_and_records_what_it_replaces(tmp_path):
    first = make_pdf(tmp_path, "hazard-probabilities.pdf", cover="First")
    second = make_pdf(tmp_path, "hazard-probabilities-version-2.pdf", cover="Second")
    latest = make_pdf(tmp_path, "Hazard Probabilities (Version 2.1).pdf", cover="Third")
    unrelated = make_pdf(tmp_path, "hazard-maps.pdf", cover="Other")

    corpus = sort_corpus([first, second, latest, unrelated])

    assert names(corpus.kept) == {latest.name, unrelated.name}
    kept_latest = next(d for d in corpus.kept if d.path == latest)
    assert set(kept_latest.replaces) == {first, second}
    assert reasons(corpus) == {first.name: OLDER_VERSION, second.name: OLDER_VERSION}


def test_copy_suffix_marks_a_newer_upload_of_the_same_file(tmp_path):
    plain = make_pdf(tmp_path, "rfp-office-cleaning.pdf", cover="First")
    again = make_pdf(tmp_path, "rfp-office-cleaning_0.pdf", cover="Second")
    third = make_pdf(tmp_path, "rfp-office-cleaning_1.pdf", cover="Third")

    corpus = sort_corpus([plain, third, again])

    assert names(corpus.kept) == {"rfp-office-cleaning_1.pdf"}
    assert reasons(corpus) == {plain.name: OLDER_VERSION, again.name: OLDER_VERSION}


def test_documents_that_only_share_a_prefix_are_not_versions_of_each_other(tmp_path):
    pdfs = [
        make_pdf(tmp_path, "figi-newsletter-april-2024.pdf", cover="April"),
        make_pdf(tmp_path, "figi-newsletter-may-2024.pdf", cover="May"),
        make_pdf(tmp_path, "wri-europe-policy-plan-2024.pdf", cover="2024"),
        make_pdf(tmp_path, "wri-europe-policy-plan-2025.pdf", cover="2025"),
        make_pdf(tmp_path, "charging-toward-2035-trucks.pdf", cover="Trucks"),
        make_pdf(tmp_path, "charging-toward-2035-vehicles.pdf", cover="Vehicles"),
    ]

    corpus = sort_corpus(pdfs)

    assert names(corpus.kept) == {pdf.name for pdf in pdfs}
    assert corpus.dropped == []


def test_same_file_name_in_two_year_folders_keeps_the_later_year_with_a_unique_doc_id(tmp_path):
    older = make_pdf(tmp_path / "2024_publications", "europe-strategy.pdf", cover="Draft")
    newer = make_pdf(tmp_path / "2026_publications", "europe-strategy.pdf", cover="Final")

    corpus = sort_corpus([newer, older])

    assert [d.path for d in corpus.kept] == [newer]
    assert corpus.kept[0].doc_id == "europe-strategy"
    assert [(d.path, d.reason) for d in corpus.dropped] == [(older, OLDER_VERSION)]


def test_two_kept_documents_with_the_same_doc_id_fail_loudly(tmp_path):
    # "plan-0" is a plan called "0", not a copy of "plan"; both would get the doc_id "plan-0".
    a = make_pdf(tmp_path, "plan-0.pdf", cover="A")
    b = make_pdf(tmp_path, "plan_0.pdf", cover="B")
    make_pdf(tmp_path, "plan.pdf", cover="C")

    with pytest.raises(ValueError, match="plan-0"):
        sort_corpus([a, b, tmp_path / "plan.pdf"])


def test_non_english_files_are_dropped_and_the_english_twin_is_kept(tmp_path):
    english = make_pdf(tmp_path, "forest-brief.pdf", ENGLISH)
    spanish = make_pdf(tmp_path, "forest-brief-espanol.pdf", SPANISH)
    french = make_pdf(tmp_path, "rapport-des-forets.pdf", FRENCH)
    chinese = make_pdf(tmp_path, "forest-brief-CN.pdf", CHINESE)

    corpus = sort_corpus([english, spanish, french, chinese])

    assert [d.path for d in corpus.kept] == [english]
    assert corpus.kept[0].language == "en"
    assert reasons(corpus) == {
        spanish.name: NOT_ENGLISH,
        french.name: NOT_ENGLISH,
        chinese.name: NOT_ENGLISH,
    }
    details = {d.path.name: d.detail for d in corpus.dropped}
    assert details[spanish.name] == "es; English twin kept: " + f"{tmp_path.name}/{english.name}"
    assert details[french.name] == "fr; no English twin found"
    assert details[chinese.name].startswith("zh; English twin kept")


def test_a_file_with_too_little_text_to_judge_is_kept_with_unknown_language(tmp_path):
    slides = make_pdf(tmp_path, "pitch-deck.pdf", body="Seedlings for sale")

    corpus = sort_corpus([slides])

    assert [(d.path, d.language) for d in corpus.kept] == [(slides, "unknown")]


@pytest.mark.parametrize(
    ("name", "cover", "expected"),
    [
        ("rfp-consultant-support.pdf", "", "RFP"),
        ("ramp-capacity-needs.pdf", "REQUEST FOR PROPOSALS", "RFP"),
        ("us-clean-energy-pulse-march-2024.pdf", "", "newsletter"),
        ("cli-hot-science-april-2026-abc123.pdf", "", "newsletter"),
        ("wri-annual-report-2024.pdf", "", "annual report"),
        ("dataset-school-bus-fleets.pdf", "", "dataset documentation"),
        ("technical-note-dataset-fleets.pdf", "", "technical note"),
        ("critical-minerals.pdf", "WORKING PAPER | Version 1.0", "working paper"),
        ("cities-heat.pdf", "TECHNICAL NOTE | Version 1.0", "technical note"),
        ("transitions-harvest.pdf", "ISSUE BRIEF", "issue brief"),
        ("beef-purchasing.pdf", "REPORT", "research report"),
        ("citing-papers.pdf", "Earlier we cited a working paper and a technical note.", "other"),
        ("plain.pdf", "", "other"),
    ],
)
def test_document_type_comes_from_the_file_name_then_the_cover(tmp_path, name, cover, expected):
    corpus = sort_corpus([make_pdf(tmp_path, name, cover=cover)])

    assert corpus.kept[0].doc_type == expected
