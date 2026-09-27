#!/usr/bin/env python
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from crewai_invoice_contract.crews.discrepancy_crew.discrepancy_crew import DiscrepancyCrew

load_dotenv()

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def kickoff():
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Add it to .env (see .env_example).")

    result = DiscrepancyCrew().crew().kickoff()

    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"discrepancy_report_{datetime.now():%Y%m%d_%H%M%S}.md"
    path.write_text(result.raw)
    print(f"\nReport saved to {path}\n")
    print(result.raw)


if __name__ == "__main__":
    kickoff()
