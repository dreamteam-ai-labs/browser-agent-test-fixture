---
name: stripe-payments
description: Stripe payment integration including subscriptions, one-time payments, webhooks, and customer portal
version: 1.0.0
triggers:
  - stripe
  - payments
  - subscription
  - checkout
  - billing
  - payment processing
  - credit card
  - invoicing
tags:
  - payments
  - stripe
  - subscriptions
  - billing
  - e-commerce
---

# Stripe Payments Integration

## Summary

**Stripe Integration Architecture:**

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend    │────▶│   Stripe    │
│  Checkout   │     │   (Webhooks) │◀────│    API      │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Database   │
                    │ (Customer/   │
                    │  Subscription│
                    │    state)    │
                    └──────────────┘
```

**Key Principles:**
1. **Never trust the client** - Use webhooks for payment confirmation
2. **Idempotency** - All payment operations should be idempotent
3. **Webhook-first** - Don't grant access until webhook confirms payment
4. **Test mode first** - Use test keys until production ready

**Required Secrets (Codespace):**
| Secret Name | Value Source | Environment |
|-------------|--------------|-------------|
| `STRIPE_SECRET_KEY` | Stripe Dashboard | Backend only |
| `STRIPE_PUBLISHABLE_KEY` | Stripe Dashboard | Frontend |
| `STRIPE_WEBHOOK_SECRET` | Stripe Dashboard > Webhooks | Backend |
| `STRIPE_PRICE_ID` | Created via API or Dashboard | Backend |

## Details

### Step 1: Install Dependencies

```bash
# Python
pip install stripe

# JavaScript/TypeScript
npm install stripe @stripe/stripe-js @stripe/react-stripe-js
```

### Step 2: Backend Configuration (FastAPI)

**config.py:**
```python
from pydantic_settings import BaseSettings
import stripe

class StripeSettings(BaseSettings):
    """Stripe configuration with environment support."""

    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_price_id: str  # Default subscription price

    # URLs for Stripe redirects
    frontend_url: str = "http://localhost:3000"
    success_url: str = "{frontend_url}/payment/success?session_id={CHECKOUT_SESSION_ID}"
    cancel_url: str = "{frontend_url}/payment/cancel"

    class Config:
        env_file = ".env"

    def get_success_url(self) -> str:
        return self.success_url.format(frontend_url=self.frontend_url)

    def get_cancel_url(self) -> str:
        return self.cancel_url.format(frontend_url=self.frontend_url)

settings = StripeSettings()

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key
```

### Step 3: Customer and Subscription Management

**models.py:**
```python
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    TRIALING = "trialing"

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True)  # Your user ID
    stripe_customer_id = Column(String, unique=True, nullable=True)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="customer")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)  # Stripe subscription ID
    customer_id = Column(String, ForeignKey("customers.id"))
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.INCOMPLETE)
    price_id = Column(String, nullable=False)
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="subscriptions")
```

**services/stripe_service.py:**
```python
import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Customer, Subscription, SubscriptionStatus
from .config import settings

class StripeService:
    """Stripe operations with database sync."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_customer(
        self, user_id: str, email: str
    ) -> tuple[Customer, str]:
        """Get or create Stripe customer for user."""
        # Check if customer exists
        customer = await self.db.get(Customer, user_id)

        if customer and customer.stripe_customer_id:
            return customer, customer.stripe_customer_id

        # Create Stripe customer
        stripe_customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id},
        )

        if customer:
            customer.stripe_customer_id = stripe_customer.id
        else:
            customer = Customer(
                id=user_id,
                email=email,
                stripe_customer_id=stripe_customer.id,
            )
            self.db.add(customer)

        await self.db.commit()
        return customer, stripe_customer.id

    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        price_id: str | None = None,
        mode: str = "subscription",  # or "payment" for one-time
    ) -> str:
        """Create Stripe Checkout session, return URL."""
        customer, stripe_customer_id = await self.get_or_create_customer(
            user_id, email
        )

        session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id or settings.stripe_price_id,
                "quantity": 1,
            }],
            mode=mode,
            success_url=settings.get_success_url(),
            cancel_url=settings.get_cancel_url(),
            metadata={"user_id": user_id},
        )

        return session.url

    async def create_portal_session(self, user_id: str) -> str:
        """Create Stripe Customer Portal session for subscription management."""
        customer = await self.db.get(Customer, user_id)
        if not customer or not customer.stripe_customer_id:
            raise ValueError("Customer not found")

        session = stripe.billing_portal.Session.create(
            customer=customer.stripe_customer_id,
            return_url=f"{settings.frontend_url}/account",
        )

        return session.url

    async def sync_subscription(self, subscription_data: dict) -> Subscription:
        """Sync subscription from Stripe webhook data."""
        sub_id = subscription_data["id"]
        customer_id = subscription_data["metadata"].get("user_id")

        if not customer_id:
            # Look up by Stripe customer ID
            stripe_customer_id = subscription_data["customer"]
            customer = await self.db.execute(
                select(Customer).where(
                    Customer.stripe_customer_id == stripe_customer_id
                )
            )
            customer = customer.scalar_one_or_none()
            if customer:
                customer_id = customer.id

        subscription = await self.db.get(Subscription, sub_id)

        if subscription:
            # Update existing
            subscription.status = SubscriptionStatus(subscription_data["status"])
            subscription.current_period_start = datetime.fromtimestamp(
                subscription_data["current_period_start"]
            )
            subscription.current_period_end = datetime.fromtimestamp(
                subscription_data["current_period_end"]
            )
            subscription.cancel_at_period_end = subscription_data["cancel_at_period_end"]
            if subscription_data.get("canceled_at"):
                subscription.canceled_at = datetime.fromtimestamp(
                    subscription_data["canceled_at"]
                )
        else:
            # Create new
            subscription = Subscription(
                id=sub_id,
                customer_id=customer_id,
                status=SubscriptionStatus(subscription_data["status"]),
                price_id=subscription_data["items"]["data"][0]["price"]["id"],
                current_period_start=datetime.fromtimestamp(
                    subscription_data["current_period_start"]
                ),
                current_period_end=datetime.fromtimestamp(
                    subscription_data["current_period_end"]
                ),
                cancel_at_period_end=subscription_data["cancel_at_period_end"],
            )
            self.db.add(subscription)

        await self.db.commit()
        return subscription

    async def get_active_subscription(self, user_id: str) -> Subscription | None:
        """Get user's active subscription."""
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.customer_id == user_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .order_by(Subscription.created_at.desc())
        )
        return result.scalar_one_or_none()
```

### Step 4: API Routes

**routes/payments.py:**
```python
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
import stripe
from .auth import verify_firebase_token, TokenData
from .services.stripe_service import StripeService
from .config import settings
from .database import get_db

router = APIRouter(prefix="/payments", tags=["payments"])

class CheckoutRequest(BaseModel):
    price_id: str | None = None
    mode: str = "subscription"

class CheckoutResponse(BaseModel):
    checkout_url: str

class PortalResponse(BaseModel):
    portal_url: str

class SubscriptionResponse(BaseModel):
    has_subscription: bool
    status: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user: TokenData = Depends(verify_firebase_token),
    db = Depends(get_db),
):
    """Create a Stripe Checkout session."""
    service = StripeService(db)

    try:
        url = await service.create_checkout_session(
            user_id=user.uid,
            email=user.email,
            price_id=request.price_id,
            mode=request.mode,
        )
        return CheckoutResponse(checkout_url=url)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    user: TokenData = Depends(verify_firebase_token),
    db = Depends(get_db),
):
    """Create a Stripe Customer Portal session."""
    service = StripeService(db)

    try:
        url = await service.create_portal_session(user.uid)
        return PortalResponse(portal_url=url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: TokenData = Depends(verify_firebase_token),
    db = Depends(get_db),
):
    """Get current user's subscription status."""
    service = StripeService(db)
    subscription = await service.get_active_subscription(user.uid)

    if not subscription:
        return SubscriptionResponse(has_subscription=False)

    return SubscriptionResponse(
        has_subscription=True,
        status=subscription.status.value,
        current_period_end=subscription.current_period_end.isoformat(),
        cancel_at_period_end=subscription.cancel_at_period_end,
    )

@router.get("/config")
async def get_stripe_config():
    """Get Stripe publishable key for frontend."""
    return {"publishableKey": settings.stripe_publishable_key}
```

### Step 5: Webhook Handler (CRITICAL)

**routes/webhooks.py:**
```python
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Annotated
import stripe
from .config import settings
from .services.stripe_service import StripeService
from .database import get_db_sync  # Webhooks may need sync session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str, Header(alias="Stripe-Signature")],
):
    """
    Handle Stripe webhooks.

    CRITICAL: This is where payment state becomes truth.
    Never trust client-side payment confirmations.
    """
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Get database session
    async with get_db_sync() as db:
        service = StripeService(db)

        # Handle event types
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            # For subscriptions, wait for subscription events
            # For one-time payments, fulfill here
            if session.get("mode") == "payment":
                await fulfill_order(session)

        elif event["type"] == "customer.subscription.created":
            subscription = event["data"]["object"]
            await service.sync_subscription(subscription)

        elif event["type"] == "customer.subscription.updated":
            subscription = event["data"]["object"]
            await service.sync_subscription(subscription)

        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            await service.sync_subscription(subscription)

        elif event["type"] == "invoice.paid":
            invoice = event["data"]["object"]
            # Subscription renewed successfully
            pass

        elif event["type"] == "invoice.payment_failed":
            invoice = event["data"]["object"]
            # Handle failed payment (send email, etc.)
            pass

    return {"status": "success"}

async def fulfill_order(session: dict):
    """Fulfill one-time purchase order."""
    # Implement your fulfillment logic
    user_id = session["metadata"].get("user_id")
    # Grant access, send confirmation, etc.
    pass
```

### Step 6: Frontend Integration (React)

**stripe.ts:**
```typescript
import { loadStripe, Stripe } from '@stripe/stripe-js';

let stripePromise: Promise<Stripe | null> | null = null;

export async function getStripe(): Promise<Stripe | null> {
  if (!stripePromise) {
    const response = await fetch('/api/payments/config');
    const { publishableKey } = await response.json();
    stripePromise = loadStripe(publishableKey);
  }
  return stripePromise;
}

export async function redirectToCheckout(priceId?: string): Promise<void> {
  const token = await getIdToken();

  const response = await fetch('/api/payments/checkout', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ price_id: priceId }),
  });

  if (!response.ok) {
    throw new Error('Failed to create checkout session');
  }

  const { checkout_url } = await response.json();
  window.location.href = checkout_url;
}

export async function redirectToPortal(): Promise<void> {
  const token = await getIdToken();

  const response = await fetch('/api/payments/portal', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to create portal session');
  }

  const { portal_url } = await response.json();
  window.location.href = portal_url;
}
```

**PricingPage.tsx:**
```tsx
import { useState } from 'react';
import { redirectToCheckout } from './stripe';

interface Plan {
  id: string;
  name: string;
  price: string;
  priceId: string;
  features: string[];
}

const plans: Plan[] = [
  {
    id: 'basic',
    name: 'Basic',
    price: '$9/month',
    priceId: 'price_basic123',
    features: ['Feature 1', 'Feature 2'],
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$29/month',
    priceId: 'price_pro456',
    features: ['All Basic features', 'Feature 3', 'Feature 4'],
  },
];

export function PricingPage() {
  const [loading, setLoading] = useState<string | null>(null);

  async function handleSubscribe(priceId: string) {
    setLoading(priceId);
    try {
      await redirectToCheckout(priceId);
    } catch (error) {
      console.error('Checkout error:', error);
      setLoading(null);
    }
  }

  return (
    <div className="pricing-grid">
      {plans.map(plan => (
        <div key={plan.id} className="pricing-card">
          <h2>{plan.name}</h2>
          <p className="price">{plan.price}</p>
          <ul>
            {plan.features.map(f => <li key={f}>{f}</li>)}
          </ul>
          <button
            onClick={() => handleSubscribe(plan.priceId)}
            disabled={loading === plan.priceId}
          >
            {loading === plan.priceId ? 'Loading...' : 'Subscribe'}
          </button>
        </div>
      ))}
    </div>
  );
}
```

## Advanced

### Subscription Access Control

**middleware.py:**
```python
from fastapi import Depends, HTTPException
from .auth import verify_firebase_token, TokenData
from .services.stripe_service import StripeService
from .database import get_db

class RequireSubscription:
    """Middleware that requires active subscription."""

    def __init__(self, allow_trial: bool = True):
        self.allow_trial = allow_trial

    async def __call__(
        self,
        user: TokenData = Depends(verify_firebase_token),
        db = Depends(get_db),
    ) -> TokenData:
        service = StripeService(db)
        subscription = await service.get_active_subscription(user.uid)

        if not subscription:
            raise HTTPException(
                status_code=403,
                detail="Subscription required",
            )

        if subscription.status == SubscriptionStatus.TRIALING and not self.allow_trial:
            raise HTTPException(
                status_code=403,
                detail="Paid subscription required (trial not accepted)",
            )

        return user

require_subscription = RequireSubscription()
require_paid = RequireSubscription(allow_trial=False)

# Usage
@app.get("/premium-feature")
async def premium_feature(user: TokenData = Depends(require_subscription)):
    return {"message": "You have access!"}
```

### Metered Billing (Usage-Based)

```python
async def report_usage(
    subscription_item_id: str,
    quantity: int,
    timestamp: int | None = None,
) -> None:
    """Report usage for metered billing."""
    stripe.SubscriptionItem.create_usage_record(
        subscription_item_id,
        quantity=quantity,
        timestamp=timestamp or int(time.time()),
        action="increment",  # or "set" for absolute value
    )

# Track API calls, storage, etc.
@app.middleware("http")
async def track_api_usage(request: Request, call_next):
    response = await call_next(request)

    # Get user's subscription item
    if hasattr(request.state, "subscription_item_id"):
        await report_usage(
            request.state.subscription_item_id,
            quantity=1,
        )

    return response
```

### Prorated Upgrades/Downgrades

```python
async def change_subscription_plan(
    subscription_id: str,
    new_price_id: str,
    proration_behavior: str = "create_prorations",
) -> dict:
    """
    Change subscription plan with proration.

    proration_behavior options:
    - "create_prorations": Charge/credit difference
    - "none": No proration (apply at period end)
    - "always_invoice": Invoice immediately
    """
    subscription = stripe.Subscription.retrieve(subscription_id)

    updated = stripe.Subscription.modify(
        subscription_id,
        items=[{
            "id": subscription["items"]["data"][0].id,
            "price": new_price_id,
        }],
        proration_behavior=proration_behavior,
    )

    return updated
```

### Codespace Secrets Setup

**1. Add Stripe secrets:**
```bash
gh secret set STRIPE_SECRET_KEY --body "sk_test_..."
gh secret set STRIPE_PUBLISHABLE_KEY --body "pk_test_..."
gh secret set STRIPE_WEBHOOK_SECRET --body "whsec_..."
gh secret set STRIPE_PRICE_ID --body "price_..."
```

**2. Configure devcontainer.json:**
```json
{
  "secrets": {
    "STRIPE_SECRET_KEY": {
      "description": "Stripe secret key (sk_test_... or sk_live_...)"
    },
    "STRIPE_PUBLISHABLE_KEY": {
      "description": "Stripe publishable key for frontend"
    },
    "STRIPE_WEBHOOK_SECRET": {
      "description": "Webhook signing secret (whsec_...)"
    },
    "STRIPE_PRICE_ID": {
      "description": "Default subscription price ID"
    }
  }
}
```

**3. Local webhook testing:**
```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe  # macOS
# or download from https://stripe.com/docs/stripe-cli

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/webhooks/stripe

# The CLI will print the webhook signing secret - use this locally
```

### Testing Payments

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_stripe():
    with patch("stripe.Customer") as mock_customer, \
         patch("stripe.checkout.Session") as mock_session:
        mock_customer.create.return_value = MagicMock(id="cus_test123")
        mock_session.create.return_value = MagicMock(
            url="https://checkout.stripe.com/test"
        )
        yield

@pytest.mark.asyncio
async def test_create_checkout(client, mock_stripe, auth_token):
    response = await client.post(
        "/payments/checkout",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={},
    )
    assert response.status_code == 200
    assert "checkout_url" in response.json()

# Test webhook signature verification
@pytest.mark.asyncio
async def test_webhook_invalid_signature(client):
    response = await client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"Stripe-Signature": "invalid"},
    )
    assert response.status_code == 400
```

## Resources

- [Stripe API Reference](https://stripe.com/docs/api)
- [Stripe Checkout](https://stripe.com/docs/payments/checkout)
- [Stripe Billing (Subscriptions)](https://stripe.com/docs/billing)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [Stripe Testing](https://stripe.com/docs/testing)
- [Stripe CLI](https://stripe.com/docs/stripe-cli)
