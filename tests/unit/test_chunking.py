import pytest

from bastion.ingestion.chunking import Chunk, chunk_blocks
from bastion.ingestion.markdown import Block, parse_markdown


def words(text: str) -> int:
    return len(text.split())


def test_small_blocks_under_one_heading_share_a_chunk():
    blocks = [Block(("A",), "one two"), Block(("A",), "three four")]

    assert chunk_blocks(blocks, words, max_tokens=10) == [Chunk(0, ("A",), "one two\n\nthree four")]


def test_blocks_under_different_headings_never_share_a_chunk():
    blocks = [Block(("A",), "one"), Block(("B",), "two")]

    chunks = chunk_blocks(blocks, words, max_tokens=10)

    assert [(c.heading_path, c.text) for c in chunks] == [(("A",), "one"), (("B",), "two")]


def test_a_new_chunk_starts_when_the_limit_would_be_exceeded():
    blocks = [Block(("A",), "one two three"), Block(("A",), "four five six")]

    chunks = chunk_blocks(blocks, words, max_tokens=4)

    assert [c.text for c in chunks] == ["one two three", "four five six"]


def test_ordinals_count_up_from_zero():
    blocks = [Block(("A",), "one"), Block(("B",), "two"), Block(("C",), "three")]

    assert [c.ordinal for c in chunk_blocks(blocks, words, max_tokens=10)] == [0, 1, 2]


def test_an_oversized_paragraph_is_split_at_sentences():
    blocks = [Block(("A",), "One two three. Four five six. Seven eight nine.")]

    chunks = chunk_blocks(blocks, words, max_tokens=6)

    assert [c.text for c in chunks] == ["One two three. Four five six.", "Seven eight nine."]


def test_an_oversized_sentence_is_split_at_words():
    chunks = chunk_blocks([Block((), "one two three four five")], words, max_tokens=2)

    assert [c.text for c in chunks] == ["one two", "three four", "five"]


def test_a_giant_unbroken_line_is_hard_split_without_losing_characters():
    line = "x" * 950

    chunks = chunk_blocks([Block((), line)], len, max_tokens=300)

    assert "".join(c.text for c in chunks) == line
    assert all(len(c.text) <= 300 for c in chunks)


def test_a_code_block_that_fits_is_never_split():
    code = "```python\na = 1\nb = 2\nc = 3\n```"
    blocks = [Block(("A",), "intro words here"), Block(("A",), code, "code")]

    chunks = chunk_blocks(blocks, words, max_tokens=11)

    assert [c.text for c in chunks] == ["intro words here", code]


def test_an_oversized_code_block_is_split_at_lines_and_each_piece_is_fenced():
    code = "```python\na = 1\nb = 2\nc = 3\nd = 4\n```"

    chunks = chunk_blocks([Block((), code, "code")], words, max_tokens=8)

    assert [c.text for c in chunks] == [
        "```python\na = 1\nb = 2\n```",
        "```python\nc = 3\nd = 4\n```",
    ]


def test_embedding_text_carries_the_heading_path():
    chunk = Chunk(0, ("Bitsandbytes", "QLoRA"), "Nested quantization saves memory.")

    assert chunk.embedding_text == "Bitsandbytes > QLoRA\n\nNested quantization saves memory."
    assert Chunk(0, (), "No heading.").embedding_text == "No heading."


def test_no_chunk_ever_exceeds_the_limit_and_no_text_is_lost():
    source = "# Guide\n\n" + "Sentence number one is here. " * 40 + "\n\n```python\n"
    source += "\n".join(f"value_{i} = compute({i})" for i in range(60)) + "\n```\n\n## Deep\n\n"
    source += "word " * 500

    chunks = chunk_blocks(parse_markdown(source), words, max_tokens=50)

    assert all(words(c.text) <= 50 for c in chunks)
    assert words(" ".join(c.text for c in chunks if "```" not in c.text)) == 40 * 5 + 500


def test_a_counter_that_cannot_be_satisfied_raises():
    with pytest.raises(ValueError, match="over 3 tokens"):
        chunk_blocks([Block((), "x")], lambda text: 99, max_tokens=3)