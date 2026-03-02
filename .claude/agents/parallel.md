---
name: parallel
description: Fan-out/fan-in execution using reliable-ai ParallelAgent pattern for concurrent task processing
---

# Parallel Agent

Use the ParallelAgent pattern from reliable-ai for concurrent execution of independent tasks with configurable result aggregation strategies.

## When to Use

- Multiple independent tasks that can run concurrently
- Data processing across multiple sources
- Consensus building from multiple perspectives
- Performance optimization through parallelization

## Usage Pattern

```python
from reliable_ai.agents import ParallelAgent, ParallelTask, AggregationStrategy
from typing import List

# Define independent tasks
async def analyze_sentiment(text: str) -> dict:
    result = await sentiment_analysis(text)
    return {"sentiment": result.label, "confidence": result.score}

async def extract_keywords(text: str) -> dict:
    keywords = await keyword_extraction(text)
    return {"keywords": keywords.terms, "importance": keywords.scores}

async def detect_language(text: str) -> dict:
    lang = await language_detection(text)
    return {"language": lang.code, "confidence": lang.probability}

# Create parallel tasks
tasks = [
    ParallelTask(name="sentiment", handler=analyze_sentiment),
    ParallelTask(name="keywords", handler=extract_keywords),
    ParallelTask(name="language", handler=detect_language)
]

# Execute with result collection
parallel_agent = ParallelAgent(
    tasks=tasks,
    aggregation_strategy=AggregationStrategy.COLLECT
)

result = await parallel_agent.run("This is a great product! I love using it.")

# Access individual task results
print(f"Sentiment: {result.task_results['sentiment']}")
print(f"Keywords: {result.task_results['keywords']}")
print(f"Language: {result.task_results['language']}")
print(f"Combined result: {result.output}")
```

## Aggregation Strategies

### COLLECT - Gather All Results
```python
# Collects all task results in a structured format
agent = ParallelAgent(tasks, AggregationStrategy.COLLECT)
result = await agent.run(input_data)
# result.output contains all task outputs combined
```

### MAJORITY_VOTE - Democratic Decision
```python
# Use when tasks produce decisions that need consensus
voting_tasks = [
    ParallelTask("classifier_1", classify_with_model_a),
    ParallelTask("classifier_2", classify_with_model_b),
    ParallelTask("classifier_3", classify_with_model_c)
]

voting_agent = ParallelAgent(tasks, AggregationStrategy.MAJORITY_VOTE)
result = await voting_agent.run("Text to classify")
# result.output contains the majority decision
```

### FIRST_SUCCESS - Race Condition
```python
# Use when any successful result is acceptable (performance optimization)
redundant_tasks = [
    ParallelTask("primary_api", call_primary_service),
    ParallelTask("backup_api", call_backup_service),
    ParallelTask("cache_lookup", check_cache)
]

racing_agent = ParallelAgent(tasks, AggregationStrategy.FIRST_SUCCESS)
result = await racing_agent.run(query)
# result.output contains the first successful response
```

### CONSENSUS - Agreement Required
```python
# Use when high confidence requires agreement
consensus_tasks = [
    ParallelTask("expert_1", expert_opinion_a),
    ParallelTask("expert_2", expert_opinion_b),
    ParallelTask("expert_3", expert_opinion_c)
]

consensus_agent = ParallelAgent(
    tasks,
    AggregationStrategy.CONSENSUS,
    consensus_threshold=0.8  # Require 80% agreement
)
result = await consensus_agent.run("Complex decision scenario")
```

## Timeout and Error Handling

```python
# Configure per-task timeouts
tasks_with_timeout = [
    ParallelTask("fast_task", quick_handler, timeout_seconds=5),
    ParallelTask("slow_task", slow_handler, timeout_seconds=30),
    ParallelTask("api_call", external_api, timeout_seconds=10)
]

agent = ParallelAgent(tasks_with_timeout, AggregationStrategy.COLLECT)

# Handle partial failures
result = await agent.run(input_data)
if result.failed_tasks:
    print(f"Failed tasks: {[task.name for task in result.failed_tasks]}")
    print(f"Successful tasks: {[task.name for task in result.successful_tasks]}")
```

## Weighted Voting

```python
from reliable_ai.agents import VotingAgent

# Voting with different weights for each participant
weighted_tasks = [
    ParallelTask("senior_expert", senior_analysis, weight=2.0),
    ParallelTask("junior_expert", junior_analysis, weight=1.0),
    ParallelTask("ai_model", model_prediction, weight=1.5)
]

voting_agent = VotingAgent(
    tasks=weighted_tasks,
    voting_strategy="weighted"  # or "simple", "ranked"
)

result = await voting_agent.run("Expert consultation scenario")
print(f"Weighted decision: {result.output}")
print(f"Vote breakdown: {result.vote_details}")
```

## Custom Aggregation

```python
class CustomParallelAgent(ParallelAgent):
    async def aggregate(self, task_results: List[ParallelResult]) -> str:
        # Custom aggregation logic
        successful_results = [r for r in task_results if r.success]

        if len(successful_results) == 0:
            return "All tasks failed"

        # Custom combination logic
        combined_data = {}
        for result in successful_results:
            combined_data[result.task_name] = result.output

        # Apply custom merging algorithm
        final_result = await custom_merge_algorithm(combined_data)
        return final_result

# Use custom aggregation
custom_agent = CustomParallelAgent(tasks)
result = await custom_agent.run(input_data)
```

## Key Features

- **Concurrent Execution**: True parallel processing for independent tasks
- **Flexible Aggregation**: Multiple strategies for combining results
- **Timeout Management**: Per-task timeout configuration
- **Error Resilience**: Graceful handling of partial failures
- **Result Tracking**: Detailed execution timing and success tracking
- **Weighted Operations**: Support for weighted voting and consensus

## Best Practices

- Ensure tasks are truly independent (no shared state dependencies)
- Set reasonable timeouts based on expected task completion times
- Choose appropriate aggregation strategy for your use case
- Handle partial failures gracefully in your application logic
- Monitor task execution times to identify performance bottlenecks
- Use weighted voting when some inputs are more authoritative than others