from dataclasses import dataclass

FENCE = "```"


@dataclass(frozen=True)
class Block:
    heading_path: tuple[str, ...]
    text: str
    kind: str = "text"


def parse_heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    level = len(stripped) - len(stripped.lstrip("#"))

    if not 1 <= level <= 6 or stripped[level : level + 1] != " ":
        return None

    return level, stripped[level:].strip().rstrip("#").strip()


def parse_markdown(source: str) -> list[Block]:
    blocks: list[Block] = []
    path: list[str] = []
    buffer: list[str] = []
    in_code = False

    def flush(kind: str) -> None:
        text = "\n".join(buffer).strip()
        if text:
            blocks.append(Block(tuple(path), text, kind))
        buffer.clear()

    for line in source.splitlines():
        if line.lstrip().startswith(FENCE):
            if in_code:
                buffer.append(line)
                flush("code")
            else:
                flush("text")
                buffer.append(line)
            in_code = not in_code
            continue

        if in_code:
            buffer.append(line)
            continue

        heading = parse_heading(line)
        if heading:
            flush("text")
            level, title = heading
            del path[level - 1 :]
            path.append(title)
            continue

        if not line.strip():
            flush("text")
            continue

        buffer.append(line)

    flush("code" if in_code else "text")
    return blocks