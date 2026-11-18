import pytest

from faqbot.chunking import chunk_folder
from faqbot.config import PROJECT_ROOT
from faqbot.retrieval import BM25Index, tokenize


@pytest.fixture(scope="module")
def index():
    return BM25Index(chunk_folder(PROJECT_ROOT / "sample_docs"))


def test_tokenize():
    assert tokenize("What are your Opening HOURS on Sundays?") == ["open", "hour", "sunday"]
    assert tokenize("the and of") == []


@pytest.mark.parametrize(
    "a,b",
    [("parking", "park"), ("cakes", "cake"), ("baked", "baking"), ("boxes", "box"), ("classes", "class"), ("bakeries", "bakery")],
)
def test_related_words_share_a_token(a, b):
    assert tokenize(a) == tokenize(b)


def test_hyphenated_words_split():
    assert tokenize("gluten-free") == tokenize("gluten free")


@pytest.mark.parametrize(
    "question,expected_heading",
    [
        ("Are you open on Mondays?", "Opening hours"),
        ("Do you have gluten-free options?", "Gluten-free and vegan options"),
        ("Do you deliver catering orders?", "Delivery"),
        ("Can I get a refund if I cancel my cake order?", "Cancellations and refunds"),
        ("Where can I park?", "Address and parking"),
        ("Do you run sourdough baking classes?", "Do you offer baking classes?"),
        ("Can I bring my dog inside?", "Pets"),
        ("Do you take Apple Pay?", "Payment"),
    ],
)
def test_top_hit_is_the_right_section(index, question, expected_heading):
    hits = index.search(question, top_k=3)
    assert hits, question
    assert hits[0].chunk.heading == expected_heading


def test_scores_sorted_and_positive(index):
    hits = index.search("croissant price", top_k=4)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(s > 0 for s in scores)


def test_unrelated_or_empty_query_returns_nothing(index):
    assert index.search("the and of") == []
    assert index.search("quantum entanglement") == []


def test_empty_index_rejected():
    with pytest.raises(ValueError):
        BM25Index([])


def test_relative_cutoff_drops_weak_matches(index):
    hits = index.search("Do you have gluten-free options?", top_k=4)
    assert [h.chunk.heading for h in hits] == ["Gluten-free and vegan options", "Allergies"]
    assert len(index.search("Do you have gluten-free options?", top_k=4, rel_cutoff=0)) == 4
