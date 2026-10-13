"""Inspect owns actor execution, retries, epochs, usage accounting and raw logs."""
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate
from hidden_agenda.data import CONDITIONS, FORMAT, actor_prompt, instances


@task
def hidden_agenda(split="dev", count=3, size=5, condition="concealment"):
    if condition not in CONDITIONS:
        raise ValueError(condition)
    return Task(dataset=[Sample(id=item["id"], input=actor_prompt(item, condition),
                                metadata={**item, "condition": condition, "public_output_format": FORMAT})
                         for item in instances(split, count, size)],
                solver=generate(), metadata={"benchmark": "hidden-agenda", "protocol_version": 1})
