from bastion.ingestion.markdown import Block, parse_markdown


def test_headings_build_a_nested_path():
    blocks = parse_markdown("# Guide\n\n## Setup\n\nInstall it.")

    assert blocks == [Block(("Guide", "Setup"), "Install it.")]


def test_a_sibling_heading_replaces_the_previous_one():
    blocks = parse_markdown("# Guide\n## Setup\nA\n## Usage\nB")

    assert [b.heading_path for b in blocks] == [("Guide", "Setup"), ("Guide", "Usage")]


def test_going_back_up_drops_the_deeper_headings():
    blocks = parse_markdown("# A\n## B\n### C\ndeep\n# D\ntop")

    assert [b.heading_path for b in blocks] == [("A", "B", "C"), ("D",)]


def test_text_before_any_heading_has_an_empty_path():
    assert parse_markdown("Just text.") == [Block((), "Just text.")]


def test_blank_lines_separate_paragraphs():
    blocks = parse_markdown("# T\n\nfirst\nstill first\n\nsecond")

    assert [b.text for b in blocks] == ["first\nstill first", "second"]


def test_a_code_fence_is_one_block():
    blocks = parse_markdown("# T\n\n```python\nx = 1\n\ny = 2\n```\n\nafter")

    assert blocks[0] == Block(("T",), "```python\nx = 1\n\ny = 2\n```", "code")
    assert blocks[1].text == "after"


def test_a_hash_inside_a_code_fence_is_not_a_heading():
    blocks = parse_markdown("# Real\n\n```python\n# a comment\nx = 1\n```\n\ntext")

    assert [b.heading_path for b in blocks] == [("Real",), ("Real",)]
    assert "# a comment" in blocks[0].text


def test_an_unclosed_fence_still_produces_a_code_block():
    blocks = parse_markdown("```\nnever closed")

    assert blocks == [Block((), "```\nnever closed", "code")]


def test_a_hashtag_without_a_space_is_not_a_heading():
    assert parse_markdown("#hashtag here") == [Block((), "#hashtag here")]