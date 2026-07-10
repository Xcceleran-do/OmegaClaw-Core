#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.semantic_parser import semantic_parse  # noqa: E402


TAXONOMY = [
    ("Garfield", "animal"),
    ("Socrates", "human"),
    ("Pingu", "penguin"),
    ("Tweety", "bird"),
    ("Rover", "robot"),
    ("Salmon", "fish"),
    ("Oak", "tree"),
    ("Aspirin", "medicine"),
]

PROPERTIES = [
    ("Pingu", "feathers"),
    ("Falcon", "wings"),
    ("Wolf", "fur"),
    ("Cobra", "venom"),
    ("The rover", "engine"),
]

PROPERTY_ADJECTIVES = {
    "engine": "motorized",
    "feathers": "feathered",
    "fur": "furred",
    "venom": "venomous",
    "wings": "winged",
}

ADJECTIVE_FACTS = [
    ("Cyanide", "toxic"),
    ("Glass", "fragile"),
    ("The server", "operational"),
    ("This bridge", "safe"),
    ("Lead", "not edible"),
]

RELATIONS = [
    ("Alice", "likes", "Bob"),
    ("Tigers", "eat", "elephants"),
    ("Doctors", "treat", "patients"),
    ("Rain", "causes", "wet grass"),
    ("Sam", "trusts", "Maya"),
    ("Cats", "do not eat", "stones"),
]

RULES = [
    "All humans are mortal.",
    "Every bird is an animal.",
    "Any penguin is a bird.",
    "All feathered things are birds.",
    "Things with wings are flying.",
    "Things with venom are dangerous.",
    "No reptiles are mammals.",
    "If something has feathers, it is a bird.",
    "If someone is a human, they are mortal.",
    "If tiger eats elephant, tiger is dangerous.",
]

SIMILARITIES = [
    ("Dogs", "wolves"),
    ("Robots", "machines"),
    ("Falcons", "hawks"),
]

QUERIES = [
    "Is Pingu a bird?",
    "Is Socrates mortal?",
    "Does tiger eat elephant?",
    "Do doctors treat patients?",
    "What animals are dangerous?",
    "Which robots are operational?",
]

MULTI_SENTENCE = [
    "Pingu has feathers. All feathered things are birds. Is Pingu a bird?",
    "Socrates is a human. All humans are mortal. Is Socrates mortal?",
    "Cobra has venom. Things with venom are dangerous. Is Cobra dangerous?",
    "Tigers eat elephants. If tiger eats elephant, tiger is dangerous. Is tiger dangerous?",
    "Garfield is an animal. Every animal is mortal. Is Garfield mortal?",
    (
        "If an article has small length and has AI topic it will have high engagement. "
        "I am about to write an article with AI topic with small length. "
        "Do you think it will be engaging?"
    ),
    "Anna is Bob's friend. If Anna is Bob's friend and Anna smokes, Bob smokes. Anna smokes. Does Bob smoke?",
    "If a robot sees a toy, it should bring it. Frisbee is a toy. Robot sees frisbee. Should robot bring frisbee?",
    "If something is really fat, it is fat. Cat is really fat. Is cat fat?",
]


def _examples():
    texts = []

    for subject, category in TAXONOMY:
        texts.append(f"{subject} is {_article(category)} {category}.")

    for subject, prop in PROPERTIES:
        texts.append(f"{subject} has {prop}.")

    for subject, prop in ADJECTIVE_FACTS:
        texts.append(f"{subject} is {prop}.")

    for subject, predicate, obj in RELATIONS:
        texts.append(f"{subject} {predicate} {obj}.")

    for left, right in SIMILARITIES:
        texts.append(f"{left} are similar to {right}.")

    texts.extend(RULES)
    texts.extend(QUERIES)
    texts.extend(MULTI_SENTENCE)

    # Compositional variations for stronger converter coverage.
    for entity, category in TAXONOMY[:5]:
        texts.append(f"{entity} is {_article(category)} {category}. Is {entity} {_article(category)} {category}?")

    for entity, prop in PROPERTIES[:4]:
        prop_word = PROPERTY_ADJECTIVES.get(prop, prop)
        texts.append(f"{entity} has {prop}. All {prop_word} things are dangerous.")

    return texts


def _article(word):
    return "an" if word[0].lower() in "aeiou" else "a"


def _split_for(index):
    if index % 10 == 0:
        return "test"
    if index % 10 == 1:
        return "validation"
    return "train"


def build_records():
    records = []
    for index, text in enumerate(_examples(), start=1):
        records.append(
            {
                "id": f"semantic-parser-{index:04d}",
                "split": _split_for(index),
                "text": text,
                "target": semantic_parse(text),
            }
        )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "datasets" / "semantic_parser_seed.jsonl"),
        help="Path to the JSONL dataset to write.",
    )
    args = parser.parse_args()

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise SystemExit("Set GEMINI_API_KEY or GOOGLE_API_KEY to generate DSPy/Gemini semantic parser labels.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    records = build_records()
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"Wrote {len(records)} records to {output}")


if __name__ == "__main__":
    main()
