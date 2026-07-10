#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.metadata_extractor import article_metadata  # noqa: E402


ARTICLES = [
    """Climate Policy Cuts Industrial Emissions
According to a 2025 agency report, carbon emissions from heavy industry fell 12 percent after factories adopted renewable energy contracts. The article argues that targeted regulation can reduce pollution without lowering output. However, the report notes uncertainty about whether smaller firms can afford the transition by 2030.""",
    """New AI Model Improves Hospital Triage
A clinical study of 4,200 patients found that an AI model improved triage accuracy by 9 percent. Researchers reported that the system was most reliable when doctors reviewed uncertain cases. The main claim is that automation can improve care when it is supervised.""",
    """Opinion: Cities Should Ban Cars Downtown
City leaders should ban private cars in dense downtown districts because traffic harms public health and slows buses. The piece argues that local policy must prioritize pedestrians, even if some drivers object. Evidence is mostly based on examples from other cities.""",
    """Chip Startup Announces Faster Database Hardware
The company said its new chip reduces database query latency by 35 percent in internal benchmarks. The launch article is optimistic and technical, but it does not include independent measurements. Customers could see lower cloud costs next year.""",
    """Market Report Warns About Inflation Risk
Analysts warned that persistent inflation could keep interest rates high through 2027. The report cites central bank data and recent price indexes. It concludes that investors should expect slower growth and higher debt costs.""",
    """Small School Tests Tutoring Program
A local school introduced a tutoring program for 80 students after math scores declined. Teachers said the early results are promising, but the article gives no controlled study. The claim is that targeted tutoring may help students recover.""",
    """Research Paper Finds Microplastics In River Fish
Scientists measured microplastic particles in 300 fish across five rivers. The study found contamination in 74 percent of samples and suggests that pollution controls are needed upstream. The tone is analytical and cautious.""",
    """Product Launch Promises The Best Project App
The company claims its new app is the best way for teams to finish work faster. The article uses enthusiastic customer quotes but provides no statistics or independent tests. It is written in a promotional style.""",
    """Court Ruling Changes Data Privacy Rules
The national court ruled that agencies must limit retention of location data. Legal experts said the decision will affect police investigations and telecom companies. The article explains the policy scope without taking a strong emotional stance.""",
    """Drought Forecast Raises Food Security Concerns
Weather models forecast below-average rainfall through 2028 in several farming regions. The article warns that drought could reduce crop yields and increase food prices. It cites satellite observations and historical rainfall data.""",
]


def _split_for(index):
    if index % 5 == 0:
        return "test"
    if index % 5 == 1:
        return "validation"
    return "train"


def build_records():
    records = []
    for index, text in enumerate(ARTICLES, start=1):
        records.append(
            {
                "id": f"article-metadata-{index:04d}",
                "split": _split_for(index),
                "text": text,
                "target": article_metadata(text),
            }
        )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "datasets" / "article_metadata_seed.jsonl"),
        help="Path to the JSONL dataset to write.",
    )
    args = parser.parse_args()

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise SystemExit("Set GEMINI_API_KEY or GOOGLE_API_KEY to generate DSPy/Gemini metadata labels.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    records = build_records()
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"Wrote {len(records)} records to {output}")


if __name__ == "__main__":
    main()
