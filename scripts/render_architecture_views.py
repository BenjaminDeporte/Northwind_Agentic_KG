"""Render the Architecture 2–4 flow views as portable JPG references."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def render(path: Path, title: str, columns: list[list[str]], branch_labels: list[str] | None = None) -> None:
    width = max(1800, 100 + len(columns) * 285 + 100)
    image = Image.new("RGB", (width, 900), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(BOLD, 34)
    box_font = ImageFont.truetype(BOLD, 22)
    label_font = ImageFont.truetype(FONT, 18)
    draw.text((70, 40), title, fill="#17202a", font=title_font)
    y = 280
    box_w, box_h = 220, 80
    gap = 65
    x_positions = [100 + i * (box_w + gap) for i in range(len(columns))]
    for col_idx, column in enumerate(columns):
        x = x_positions[col_idx]
        if len(column) == 1:
            ys = [y]
        else:
            ys = [y - 75, y + 75]
        for row_idx, label in enumerate(column):
            yy = ys[row_idx]
            fill = "#d9eaf7" if label not in {"reflection", "curated selection"} else "#fce4ec"
            draw.rounded_rectangle((x, yy, x + box_w, yy + box_h), radius=14, fill=fill, outline="#315b7d", width=3)
            bbox = draw.multiline_textbbox((0, 0), label, font=box_font, align="center")
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.multiline_text((x + (box_w - tw) / 2, yy + (box_h - th) / 2), label, fill="#17202a", font=box_font, align="center")
    for idx in range(len(columns) - 1):
        x1 = x_positions[idx] + box_w
        x2 = x_positions[idx + 1]
        if len(columns[idx + 1]) == 1:
            y1, y2 = y + box_h / 2, y + box_h / 2
            draw.line((x1, y1, x2, y2), fill="#495057", width=4)
            draw.polygon([(x2, y2), (x2 - 14, y2 - 9), (x2 - 14, y2 + 9)], fill="#495057")
        else:
            for row_idx, yy in enumerate([y - 75, y + 75]):
                y1 = y + box_h / 2
                y2 = yy + box_h / 2
                draw.line((x1, y1, x2, y2), fill="#495057", width=4)
                draw.polygon([(x2, y2), (x2 - 14, y2 - 9), (x2 - 14, y2 + 9)], fill="#495057")
    if branch_labels:
        for idx, label in enumerate(branch_labels):
            x = x_positions[idx + 1] - 30
            draw.text((x, y - 125 if idx == 0 else y + 165), label, fill="#495057", font=label_font)
    draw.text((70, 780), "Shared boundaries: read-only Cypher validation, Neo4j execution, MLflow logging", fill="#495057", font=label_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=95)


def main() -> None:
    render(
        ROOT / "architectures/generic_reflection/GRAPH.jpg",
        "Architecture 2 — Generic Text2Cypher with Self-Reflection",
        [["router"], ["agent"], ["Text2Cypher"], ["validation"], ["Neo4j"], ["answer"], ["reflection", "agent"]],
        ["pass → terminal", "fail → agent"],
    )
    render(
        ROOT / "architectures/curated/GRAPH.jpg",
        "Architecture 3 — Curated Tools with Text2Cypher Fallback",
        [["router"], ["agent"], ["curated selection", "Text2Cypher"], ["curated query", "validation"], ["Neo4j"], ["answer"]],
        ["match", "fallback"],
    )
    render(
        ROOT / "architectures/curated_reflection/GRAPH.jpg",
        "Architecture 4 — Curated Fallback with Self-Reflection",
        [["router"], ["agent"], ["curated selection", "Text2Cypher"], ["curated query", "validation"], ["Neo4j"], ["answer"], ["reflection", "agent"]],
        ["pass → terminal", "fail → agent"],
    )


if __name__ == "__main__":
    main()
