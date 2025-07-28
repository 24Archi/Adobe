#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
from processor import process_pdf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(p for p in in_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print("No PDFs found in input_dir", file=sys.stderr)

    for pdf_path in pdfs:
        if args.verbose: print(f"Processing {pdf_path.name}...", file=sys.stderr)
        try:
            result = process_pdf(pdf_path)
        except Exception as e:
            print(f"ERROR processing {pdf_path.name}: {e}", file=sys.stderr)
            result = {"title": None, "outline": []}
        out_path = out_dir / (pdf_path.stem + ".json")
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main() 