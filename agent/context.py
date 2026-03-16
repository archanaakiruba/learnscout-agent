"""
Context manager — controls what goes into each prompt.

Strategy:
- System prompt: always included (static)
- Plan: always included as compact JSON (task list with statuses)
- Completed task summaries: collapsed to one-liner each, max last 8
- Current task result: full summary (up to 300 words)
- Raw tool outputs: never stored — only their summaries
"""

from dataclasses import dataclass, field


@dataclass
class TaskResult:
    task_id: int
    task: str
    summary: str


@dataclass
class AgentContext:
    goal: str
    summaries: list[TaskResult] = field(default_factory=list)

    def add_result(self, task_id: int, task: str, summary: str):
        self.summaries.append(TaskResult(task_id, task, summary))

    def build_context_string(self, max_summaries: int = 8) -> str:
        """Build a compact context string from recent task summaries."""
        if not self.summaries:
            return "No tasks completed yet."

        recent = self.summaries[-max_summaries:]
        lines = []
        for r in recent:
            lines.append(f"[Task {r.task_id}] {r.task}\n→ {r.summary}")

        return "\n\n".join(lines)

    def get_plan_summary(self, plan: list[dict]) -> str:
        """Return a compact one-line-per-task plan view."""
        lines = []
        for task in plan:
            status = task["status"]
            symbol = {"pending": "○", "in_progress": "◉", "done": "✓", "failed": "✗"}.get(status, "?")
            lines.append(f"{symbol} [{task['id']}] {task['task']} ({task['tool']})")
        return "\n".join(lines)
