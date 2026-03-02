---
name: chain
description: Sequential processing pipeline using reliable-ai ChainAgent pattern for step-by-step workflows
---

# Chain Agent

Use the ChainAgent pattern from reliable-ai for sequential processing pipelines where each step's output becomes the next step's input.

## When to Use

- Multi-step workflows requiring sequential processing
- Data transformation pipelines
- Document processing workflows (extract → analyze → summarize)
- Any process with clear sequential dependencies

## Usage Pattern

```python
from reliable_ai.agents import ChainAgent, ChainStep
from typing import Any

class ExtractStep(ChainStep):
    async def process(self, input_data: str) -> dict:
        # Extract structured data from raw input
        extracted = await extract_entities(input_data)
        return {
            "entities": extracted.entities,
            "raw_text": input_data,
            "extraction_confidence": extracted.confidence
        }

    async def validate(self, result: dict) -> bool:
        # Optional validation - step fails if returns False
        return result["extraction_confidence"] > 0.7

class AnalyzeStep(ChainStep):
    async def process(self, input_data: dict) -> dict:
        # Analyze extracted entities
        analysis = await analyze_entities(input_data["entities"])
        return {
            **input_data,  # Pass through previous data
            "analysis": analysis.insights,
            "sentiment": analysis.sentiment,
            "topics": analysis.topics
        }

class SummarizeStep(ChainStep):
    async def process(self, input_data: dict) -> str:
        # Final summary generation
        summary = await generate_summary(
            text=input_data["raw_text"],
            analysis=input_data["analysis"],
            sentiment=input_data["sentiment"]
        )
        return summary

# Create processing chain
chain = ChainAgent(steps=[
    ExtractStep(),
    AnalyzeStep(),
    SummarizeStep()
])

# Execute sequential pipeline
result = await chain.run("Long document text to process...")
print(f"Final summary: {result.output}")

# Access intermediate results
for i, step_result in enumerate(result.intermediate_outputs):
    print(f"Step {i+1} result: {step_result}")
```

## Dynamic Chain Planning

For complex workflows, use DynamicChainAgent to plan steps based on input:

```python
class DocumentProcessor(DynamicChainAgent):
    async def plan_steps(self, input_data: str) -> List[ChainStep]:
        steps = [ExtractStep()]

        # Add steps based on content analysis
        if "financial" in input_data.lower():
            steps.append(FinancialAnalysisStep())
        elif "legal" in input_data.lower():
            steps.append(LegalAnalysisStep())

        steps.append(SummarizeStep())
        return steps

# Dynamic step planning based on input
processor = DocumentProcessor()
result = await processor.run("Financial report for Q3...")
```

## Key Features

- **Sequential Processing**: Guaranteed step order execution
- **Data Flow**: Each step's output becomes next step's input
- **Validation Gates**: Optional validation at each step with failure handling
- **Intermediate Access**: Access outputs from any step in the chain
- **Dynamic Planning**: Runtime step selection with DynamicChainAgent
- **Failure Handling**: Continue or fail-fast options on step failures

## Validation and Error Handling

```python
class ValidatedStep(ChainStep):
    async def process(self, input_data: Any) -> dict:
        result = await do_processing(input_data)
        return result

    async def validate(self, result: dict) -> bool:
        # Validation logic
        return result.get("quality_score", 0) > 0.8

# Configure failure behavior
chain = ChainAgent(
    steps=[ValidatedStep()],
    fail_fast=True  # Stop on first validation failure
)
```

## Best Practices

- Design steps with clear input/output contracts
- Use validation for quality gates and error detection
- Pass through useful data from previous steps
- Consider step granularity - neither too fine nor too coarse
- Handle partial failures gracefully with appropriate error messages
- Use DynamicChainAgent when step selection depends on runtime analysis