---
name: orchestrator
description: Parallel subagent coordination using reliable-ai OrchestratorAgent pattern for complex multi-step tasks
---

# Orchestrator Agent

Use the OrchestratorAgent pattern from reliable-ai for coordinating parallel subtasks with multiple workers.

## When to Use

- Breaking complex tasks into independent parallel subtasks
- Coordinating multiple specialized workers (search, analysis, generation)
- Tasks that benefit from parallel execution and result synthesis

## Usage Pattern

```python
from reliable_ai.agents import OrchestratorAgent, Worker, WorkerResult

class SearchWorker(Worker):
    async def process(self, task: str) -> WorkerResult:
        # Implement search logic
        results = await search_knowledge_base(task)
        return WorkerResult(
            worker_name="search",
            output=f"Found {len(results)} relevant documents",
            metadata={"result_count": len(results)}
        )

class AnalysisWorker(Worker):
    async def process(self, task: str) -> WorkerResult:
        # Implement analysis logic
        analysis = await analyze_content(task)
        return WorkerResult(
            worker_name="analysis",
            output=f"Analysis complete: {analysis.summary}",
            metadata={"confidence": analysis.confidence}
        )

# Create orchestrator with workers
orchestrator = OrchestratorAgent(
    workers=[SearchWorker(), AnalysisWorker()],
    max_parallel_workers=2
)

# Execute task with parallel coordination
result = await orchestrator.run("Research quantum computing applications")
print(f"Orchestration complete: {result.output}")
```

## Key Features

- **Parallel Execution**: Workers run concurrently for faster completion
- **Result Synthesis**: Automatically combines worker outputs
- **Priority Batching**: Control worker execution order and batching
- **Error Handling**: Graceful failure handling with detailed error reporting
- **Progress Tracking**: Monitor individual worker progress and overall completion

## Implementation Methods

Override these methods to customize orchestrator behavior:

```python
class CustomOrchestrator(OrchestratorAgent):
    async def plan_tasks(self, input_data) -> List[WorkerTask]:
        # Custom task planning logic
        return tasks

    async def synthesize(self, worker_results: List[WorkerResult]) -> str:
        # Custom result synthesis logic
        return combined_output
```

## Best Practices

- Keep workers focused on single responsibilities
- Use metadata in WorkerResult for rich context passing
- Implement proper error handling in worker.process() methods
- Consider worker dependencies when setting max_parallel_workers
- Use meaningful worker names for better orchestration tracking