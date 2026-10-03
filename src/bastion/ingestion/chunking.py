import re
from collections.abc import Callable
from dataclasses import dataclass

from bastion.ingestion.markdown import FENCE, Block

MAX_TOKENS = 350
HARD_SPLIT_CHARS = 100
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

TokenCounter = Callable[[str], int]
Fits = Callable[[str], bool]


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading_path: tuple[str, ...]
    text: str

    @property
    def embedding_text(self) -> str:
        header = " > ".join(self.heading_path)
        return f"{header}\n\n{self.text}" if header else self.text


def pack(units: list[str], joiner: str, fits: Fits) -> list[str]:
    groups: list[str] = []
    current: list[str] = []

    for unit in units:
        if current and not fits(joiner.join([*current, unit])):
            groups.append(joiner.join(current))
            current = []
        current.append(unit)

    if current:
        groups.append(joiner.join(current))

    return groups


def hard_split(text: str, fits: Fits) -> list[str]:
    size = HARD_SPLIT_CHARS

    while size > 1 and not all(fits(text[i : i + size]) for i in range(0, len(text), size)):
        size //= 2

    return pack([text[i : i + size] for i in range(0, len(text), size)], "", fits)


def split_text(text: str, fits: Fits) -> list[str]:
    if fits(text):
        return [text]

    for units, joiner in (
        (text.split("\n"), "\n"),
        (SENTENCE_END.split(text), " "),
        (text.split(" "), " "),
    ):
        units = [unit for unit in units if unit]
        if len(units) > 1:
            parts = [part for unit in units for part in split_text(unit, fits)]
            return pack(parts, joiner, fits)

    return hard_split(text, fits)


def split_code(text: str, fits: Fits) -> list[str]:
    if fits(text):
        return [text]

    lines = text.split("\n")
    opening = lines[0]
    body = lines[1:-1] if lines[-1].lstrip().startswith(FENCE) else lines[1:]

    def wrap(code: str) -> str:
        return f"{opening}\n{code}\n{FENCE}"

    def body_fits(code: str) -> bool:
        return fits(wrap(code))

    parts: list[str] = []
    for line in body:
        parts.extend([line] if body_fits(line) else hard_split(line, body_fits))

    return [wrap(group) for group in pack(parts, "\n", body_fits)]


def chunk_blocks(
    blocks: list[Block], count_tokens: TokenCounter, max_tokens: int = MAX_TOKENS
) -> list[Chunk]:
    def fits(text: str) -> bool:
        return count_tokens(text) <= max_tokens

    chunks: list[Chunk] = []
    path: tuple[str, ...] = ()
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append(Chunk(len(chunks), path, "\n\n".join(current)))
            current.clear()

    for block in blocks:
        split = split_code if block.kind == "code" else split_text

        for part in split(block.text, fits):
            if current and (block.heading_path != path or not fits("\n\n".join([*current, part]))):
                flush()
            path = block.heading_path
            current.append(part)

    flush()

    for chunk in chunks:
        if not fits(chunk.text):
            raise ValueError(f"chunk {chunk.ordinal} is over {max_tokens} tokens")

    return chunks