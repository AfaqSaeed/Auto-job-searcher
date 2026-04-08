"""Profile file ingestion utilities."""

from __future__ import annotations

import re
from pathlib import Path

from job_searcher.schemas import DocumentSection, ProfileDocument


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def split_markdown_sections(text: str) -> list[DocumentSection]:
    """Split Markdown or plain text into section objects while preserving order."""

    sections: list[DocumentSection] = []
    current_heading = "Introduction"
    current_level = 1
    buffer: list[str] = []

    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            if buffer:
                sections.append(
                    DocumentSection(
                        heading=current_heading,
                        level=current_level,
                        content="\n".join(buffer).strip(),
                    )
                )
                buffer = []
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
            continue
        buffer.append(line)

    if buffer or not sections:
        sections.append(
            DocumentSection(
                heading=current_heading,
                level=current_level,
                content="\n".join(buffer).strip(),
            )
        )
    return [section for section in sections if section.content or section.heading]


def read_profile_document(main_profile: Path, supplemental_files: list[Path] | None = None) -> ProfileDocument:
    """Read the main profile and optional supplements into a structured document."""

    files = [main_profile, *(supplemental_files or [])]
    chunks: list[str] = []
    source_files: list[str] = []
    sections: list[DocumentSection] = []
    for path in files:
        content = path.read_text(encoding="utf-8")
        chunks.append(content)
        source_files.append(str(path))
        sections.extend(split_markdown_sections(content))
    combined = "\n\n".join(chunks).strip()
    return ProfileDocument(source_files=source_files, raw_text=combined, sections=sections)
