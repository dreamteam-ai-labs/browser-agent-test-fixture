---
name: router
description: Classification-based routing using reliable-ai RouterAgent pattern for intent-based task delegation
---

# Router Agent

Use the RouterAgent pattern from reliable-ai for intelligent routing of requests to specialized handlers based on classification and intent detection.

## When to Use

- Customer support ticket routing to specialized teams
- Content classification and workflow assignment
- Multi-domain chatbots with specialized capabilities
- Task delegation based on complexity or type analysis

## Usage Pattern

```python
from reliable_ai.agents import RouterAgent, Route, RoutingDecision
from typing import Callable, Awaitable

# Define specialized handlers
async def technical_support_handler(request: str) -> str:
    return await handle_technical_issue(request)

async def billing_support_handler(request: str) -> str:
    return await handle_billing_inquiry(request)

async def general_inquiry_handler(request: str) -> str:
    return await handle_general_question(request)

class CustomerSupportRouter(RouterAgent):
    def __init__(self):
        routes = [
            Route(
                name="technical_support",
                handler=technical_support_handler,
                keywords=["error", "bug", "crash", "not working", "broken"],
                priority=1,
                metadata={"department": "engineering", "sla": "4_hours"}
            ),
            Route(
                name="billing_support",
                handler=billing_support_handler,
                keywords=["payment", "invoice", "bill", "charge", "refund"],
                priority=1,
                metadata={"department": "finance", "sla": "24_hours"}
            ),
            Route(
                name="general_inquiry",
                handler=general_inquiry_handler,
                keywords=[],  # Default route
                priority=3,
                metadata={"department": "general", "sla": "48_hours"}
            )
        ]
        super().__init__(routes=routes, confidence_threshold=0.7)

    async def classify(self, request: str) -> RoutingDecision:
        # Custom classification logic (override for advanced routing)
        # This could use ML models, LLMs, or rule-based classification
        classification_prompt = f"""
        Classify this customer request into categories:
        - technical_support: Technical issues, bugs, errors
        - billing_support: Payment, billing, financial questions
        - general_inquiry: General questions, information requests

        Request: {request}

        Return classification with confidence 0.0-1.0
        """

        result = await llm_call(classification_prompt)

        return RoutingDecision(
            route_name=result.category,
            confidence=result.confidence,
            alternatives=[
                {"route": alt.name, "confidence": alt.confidence}
                for alt in result.alternatives
            ],
            reasoning=result.reasoning
        )

# Execute routing
router = CustomerSupportRouter()
result = await router.run("My payment failed and I can't access my account")

print(f"Routed to: {result.selected_route.name}")
print(f"Confidence: {result.confidence}")
print(f"Response: {result.output}")
```

## Keyword-Based Routing

For simpler use cases, use the built-in KeywordRouterAgent:

```python
from reliable_ai.agents import KeywordRouterAgent

# Simple keyword-based routing
router = KeywordRouterAgent(routes=[
    Route("code_review", code_review_handler, ["review", "code", "pull request"]),
    Route("documentation", docs_handler, ["docs", "documentation", "readme"]),
    Route("testing", test_handler, ["test", "testing", "qa", "bug"])
])

result = await router.run("Please review my code changes")
# Automatically routes based on keyword matching
```

## Key Features

- **Flexible Classification**: Override classify() for custom routing logic
- **Confidence Scoring**: Route only when confidence exceeds threshold
- **Priority Ordering**: Higher priority routes considered first
- **Alternative Routing**: Access alternative routing suggestions
- **Metadata Support**: Rich route metadata for context and tracking
- **Default Routes**: Fallback handling for unclassified requests

## Advanced Classification

```python
class MLBasedRouter(RouterAgent):
    async def classify(self, request: str) -> RoutingDecision:
        # Use trained ML model for classification
        features = await extract_features(request)
        prediction = await ml_model.predict(features)

        return RoutingDecision(
            route_name=prediction.label,
            confidence=prediction.probability,
            alternatives=prediction.alternatives,
            reasoning=f"ML classification based on features: {features}"
        )

class MultiStageRouter(RouterAgent):
    async def classify(self, request: str) -> RoutingDecision:
        # Multi-stage classification: keyword filtering + ML refinement

        # Stage 1: Quick keyword filtering
        keyword_match = await self.keyword_classification(request)
        if keyword_match.confidence > 0.9:
            return keyword_match

        # Stage 2: ML-based classification for ambiguous cases
        ml_result = await self.ml_classification(request)
        return ml_result
```

## Best Practices

- Set appropriate confidence_threshold to avoid misrouting
- Provide meaningful default routes for unclassified requests
- Use route metadata for tracking, SLA management, and analytics
- Implement fallback logic for low-confidence classifications
- Monitor routing decisions to identify classification improvement opportunities
- Consider multi-stage routing for complex classification scenarios