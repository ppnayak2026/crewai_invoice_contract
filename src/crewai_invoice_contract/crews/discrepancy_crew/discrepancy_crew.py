from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai.tasks.task_output import TaskOutput

from crewai_invoice_contract.tools.document_tools import (
    compute_discrepancies,
    read_contract_text,
    read_invoice_text,
)

REPORT_SECTIONS = [
    "## Summary",
    "## Line Item Discrepancies",
    "## Scope Differences",
    "## Terms & Math Checks",
    "## Recommendation",
]


def validate_discrepancy_report(result: TaskOutput) -> tuple[bool, Any]:
    """Reject reports that skip a required section."""
    text = result.raw
    missing = [s for s in REPORT_SECTIONS if s not in text]
    if missing:
        return False, f"Report is missing required sections: {', '.join(missing)}. Use the exact headings."
    return True, result


@CrewBase
class DiscrepancyCrew:
    """Extracts contract and invoice data and produces a discrepancy report."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def contract_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["contract_analyst"],  # type: ignore[index]
            verbose=True,
        )

    @agent
    def invoice_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["invoice_analyst"],  # type: ignore[index]
            verbose=True,
        )

    @agent
    def discrepancy_auditor(self) -> Agent:
        return Agent(
            config=self.agents_config["discrepancy_auditor"],  # type: ignore[index]
            verbose=True,
        )

    @task
    def extract_contract_task(self) -> Task:
        return Task(
            config=self.tasks_config["extract_contract_task"],  # type: ignore[index]
            tools=[read_contract_text],
        )

    @task
    def extract_invoice_task(self) -> Task:
        return Task(
            config=self.tasks_config["extract_invoice_task"],  # type: ignore[index]
            tools=[read_invoice_text],
        )

    @task
    def compare_and_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["compare_and_report_task"],  # type: ignore[index]
            tools=[compute_discrepancies],
            markdown=True,
            guardrail=validate_discrepancy_report,
            guardrail_max_retries=3,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the invoice/contract discrepancy crew."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
