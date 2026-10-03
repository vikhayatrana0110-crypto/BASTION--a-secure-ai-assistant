from bastion.ingestion.chunking import MAX_TOKENS, chunk_blocks
from bastion.ingestion.markdown import parse_markdown
from bastion.ingestion.tokenizer import count_tokens, fits_the_model


def test_counts_real_tokens():
    assert count_tokens("hello world") == 2
    assert count_tokens("") == 0


def test_long_text_is_not_truncated_at_the_model_limit():
    assert count_tokens("word " * 1000) == 1000


def test_code_costs_far_more_tokens_than_words():
    line = (
        'model = AutoModelForCausalLM.from_pretrained('
        '"meta-llama/Llama-2-7b-hf", load_in_4bit=True)'
    )

    assert count_tokens(line) > 5 * len(line.split())


def test_fits_the_model_leaves_room_for_the_two_special_tokens():
    assert fits_the_model("word " * 510) is True
    assert fits_the_model("word " * 511) is False


def test_real_chunks_fit_the_embedding_model_with_their_heading():
    code = "\n".join(
        f'config_{i} = BitsAndBytesConfig(load_in_4bit=True, id="{i}")' for i in range(80)
    )
    source = (
        "# Bitsandbytes\n\n## QLoRA\n\n### Loading in 4-bit\n\n"
        + "Nested quantization saves an additional 0.4 bits per parameter. " * 90
        + f"\n\n```python\n{code}\n```\n"
    )

    chunks = chunk_blocks(parse_markdown(source), count_tokens)

    assert len(chunks) > 5
    assert all(count_tokens(chunk.text) <= MAX_TOKENS for chunk in chunks)
    assert all(fits_the_model(chunk.embedding_text) for chunk in chunks)