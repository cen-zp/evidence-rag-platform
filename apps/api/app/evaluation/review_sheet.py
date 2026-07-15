import argparse
from pathlib import Path

from app.evaluation.review import write_review_sheet
from app.evaluation.runner import load_cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a blank human-review worksheet for an evaluation JSONL file"
    )
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    write_review_sheet(cases, args.output)
    print(f"Created review worksheet with {len(cases)} case(s): {args.output}")


if __name__ == "__main__":
    main()
