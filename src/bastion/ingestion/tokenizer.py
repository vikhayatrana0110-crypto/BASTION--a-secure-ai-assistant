from functools import lru_cache

from tokenizers import Tokenizer

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
MODEL_MAX_TOKENS = 512
SPECIAL_TOKENS = 2


@lru_cache
def get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(EMBEDDING_MODEL, revision=EMBEDDING_REVISION)


def count_tokens(text: str) -> int:
    return len(get_tokenizer().encode(text, add_special_tokens=False).ids)


def fits_the_model(text: str) -> bool:
    return count_tokens(text) + SPECIAL_TOKENS <= MODEL_MAX_TOKENS