---
name: evaluator
description: Iterative refinement with feedback loops using reliable-ai EvaluatorAgent pattern for quality improvement
---

# Evaluator Agent

Use the EvaluatorAgent pattern from reliable-ai for iterative refinement through evaluation and optimization cycles.

## When to Use

- Improving content quality through iterative feedback
- Tasks requiring multiple refinement rounds until quality threshold met
- Code optimization, content editing, or design improvement workflows
- Quality assurance processes with measurable success criteria

## Usage Pattern

```python
from reliable_ai.agents import EvaluatorAgent
from reliable_ai.agents.evaluator import EvaluationContext, RefinementContext

class CodeEvaluator(EvaluatorAgent):
    def __init__(self):
        super().__init__(
            target_score=0.85,  # Minimum acceptable quality
            max_iterations=5    # Maximum refinement rounds
        )

    async def generate(self, task: str) -> str:
        # Initial generation logic
        prompt = f"Generate Python code for: {task}"
        code = await llm_call(prompt)
        return code

    async def evaluate(self, content: str, context: EvaluationContext) -> float:
        # Evaluation logic - return score 0.0-1.0
        criteria = [
            "Code correctness",
            "Code readability",
            "Performance efficiency",
            "Error handling"
        ]

        eval_prompt = f"""
        Evaluate this code on criteria: {criteria}
        Code: {content}

        Return score 0.0-1.0 and detailed feedback.
        """

        result = await llm_call(eval_prompt)
        return result.score  # Extract score from evaluation

    async def refine(self, content: str, context: RefinementContext) -> str:
        # Refinement logic based on feedback
        refine_prompt = f"""
        Improve this code based on feedback:
        Code: {content}
        Feedback: {context.feedback}
        Score: {context.score}

        Address the issues and return improved code.
        """

        improved_code = await llm_call(refine_prompt)
        return improved_code

# Execute iterative refinement
evaluator = CodeEvaluator()
result = await evaluator.run("Create a function to validate email addresses")

print(f"Final result after {result.iterations} iterations:")
print(f"Quality score: {result.final_score}")
print(f"Code: {result.output}")
```

## Key Features

- **Quality Threshold**: Automatically stops when target score reached
- **Iteration Limiting**: Prevents infinite loops with max_iterations
- **Evaluation History**: Tracks all evaluation scores and feedback over time
- **Context Passing**: Rich context objects for evaluation and refinement
- **Flexible Scoring**: Support for any 0.0-1.0 scoring mechanism

## Context Objects

**EvaluationContext**:
- `iteration`: Current iteration number
- `history`: Previous evaluation results
- `initial_content`: Original input for comparison

**RefinementContext**:
- `score`: Current evaluation score
- `feedback`: Detailed evaluation feedback
- `iteration`: Current iteration number
- `evaluation_history`: All previous evaluations

## Best Practices

- Set realistic target_score based on your quality requirements
- Provide specific, actionable feedback in evaluate() method
- Use evaluation_history to avoid repeated issues
- Implement timeout handling for long-running evaluations
- Log intermediate results for debugging refinement cycles