---
name: gcp-auth
description: GCP Identity Platform authentication with Firebase Auth, including two-credential architecture for secure deployments
version: 1.0.0
triggers:
  - gcp auth
  - google auth
  - firebase auth
  - identity platform
  - google sign in
  - gcp authentication
  - firebase authentication
  - google cloud auth
tags:
  - authentication
  - gcp
  - firebase
  - security
  - identity
---

# GCP Authentication with Identity Platform

## Summary

**CRITICAL: Two-Credential Architecture Required**

GCP Identity Platform requires TWO separate credentials:
1. **Service Account** (server-side) - For admin operations, token verification
2. **API Key** (client-side) - For Firebase Auth SDK initialization

**SECURITY WARNING:** Missing the API key restriction allows ANY password to be accepted. This is the #1 security mistake in GCP auth implementations.

**Architecture:**
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Client App    │────▶│   Your Backend   │────▶│ GCP Identity    │
│ (Firebase Auth) │     │  (FastAPI/Node)  │     │    Platform     │
│   Uses API Key  │     │ Uses Svc Account │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Required Secrets (Codespace):**
| Secret Name | Value Source | Used By |
|-------------|--------------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Service account JSON | Backend |
| `GCP_API_KEY` | API key with restrictions | Frontend |
| `GCP_PROJECT_ID` | Your GCP project ID | Both |

## Details

### Step 1: Enable Identity Platform

```bash
# Enable APIs
gcloud services enable identitytoolkit.googleapis.com
gcloud services enable iap.googleapis.com

# Enable Identity Platform in console
# https://console.cloud.google.com/customer-identity
```

### Step 2: Create Service Account (Backend)

```bash
# Create service account
gcloud iam service-accounts create firebase-auth-admin \
    --display-name="Firebase Auth Admin"

# Grant roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:firebase-auth-admin@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/firebaseauth.admin"

# Create and download key
gcloud iam service-accounts keys create service-account.json \
    --iam-account=firebase-auth-admin@$PROJECT_ID.iam.gserviceaccount.com
```

### Step 3: Create API Key (Frontend)

```bash
# Create API key via Console:
# https://console.cloud.google.com/apis/credentials

# CRITICAL: Restrict the API key!
# 1. Application restrictions: HTTP referrers
# 2. Add your domains: *.your-domain.com, localhost:*
# 3. API restrictions: Identity Toolkit API only
```

### Step 4: Backend Implementation (FastAPI)

**config.py:**
```python
from pydantic_settings import BaseSettings
import json
import os
from pathlib import Path

class Settings(BaseSettings):
    """GCP Auth settings with Codespace support."""

    gcp_project_id: str
    gcp_api_key: str  # For client config endpoint

    # Service account can be path or JSON string
    google_application_credentials: str | None = None
    google_application_credentials_json: str | None = None

    class Config:
        env_file = ".env"

    def setup_credentials(self) -> None:
        """Setup service account credentials from JSON string or file."""
        if self.google_application_credentials_json:
            # Codespace: credentials passed as JSON string
            creds_path = Path("/tmp/gcp-credentials.json")
            creds_path.write_text(self.google_application_credentials_json)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
        elif self.google_application_credentials:
            # Local: credentials file path
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_application_credentials

settings = Settings()
settings.setup_credentials()
```

**auth.py:**
```python
from fastapi import Depends, HTTPException, status, Header
from firebase_admin import auth, credentials, initialize_app
from pydantic import BaseModel
from typing import Annotated
import firebase_admin

# Initialize Firebase Admin
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    initialize_app(cred)

class TokenData(BaseModel):
    """Decoded token payload."""
    uid: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None

async def verify_firebase_token(
    authorization: Annotated[str | None, Header()] = None
) -> TokenData:
    """
    Verify Firebase ID token from Authorization header.

    Usage:
        @app.get("/protected")
        async def protected(user: TokenData = Depends(verify_firebase_token)):
            return {"uid": user.uid}
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Use: Bearer <token>",
        )

    token = authorization[7:]  # Remove "Bearer "

    try:
        decoded = auth.verify_id_token(token)
        return TokenData(
            uid=decoded["uid"],
            email=decoded.get("email"),
            email_verified=decoded.get("email_verified", False),
            name=decoded.get("name"),
            picture=decoded.get("picture"),
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
        )


class RequireEmailVerified:
    """Dependency that requires email verification."""

    async def __call__(
        self, user: TokenData = Depends(verify_firebase_token)
    ) -> TokenData:
        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required",
            )
        return user

require_verified = RequireEmailVerified()
```

**IMPORTANT: Pre-existing tenant users.** The GCP tenant may already contain users that were not registered through your app. Your login endpoint must handle this: if GCP authentication succeeds but no local DB record exists, auto-create one from the token data (uid, email, display name).

**routes/auth.py:**
```python
from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth
from pydantic import BaseModel, EmailStr
from .auth import verify_firebase_token, TokenData
from .config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

class FirebaseConfig(BaseModel):
    """Client-side Firebase configuration."""
    apiKey: str
    authDomain: str
    projectId: str

class UserCreate(BaseModel):
    """Create user request."""
    email: EmailStr
    password: str
    display_name: str | None = None

class UserResponse(BaseModel):
    """User response."""
    uid: str
    email: str
    display_name: str | None
    email_verified: bool

@router.get("/config", response_model=FirebaseConfig)
async def get_firebase_config():
    """
    Get Firebase configuration for client-side initialization.

    This endpoint provides the API key that clients need to
    initialize Firebase Auth SDK.
    """
    return FirebaseConfig(
        apiKey=settings.gcp_api_key,
        authDomain=f"{settings.gcp_project_id}.firebaseapp.com",
        projectId=settings.gcp_project_id,
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user(user: TokenData = Depends(verify_firebase_token)):
    """Get current authenticated user."""
    return UserResponse(
        uid=user.uid,
        email=user.email or "",
        display_name=user.name,
        email_verified=user.email_verified,
    )

@router.post("/users", response_model=UserResponse)
async def create_user(user_data: UserCreate):
    """
    Create a new user (admin operation).

    Note: For self-registration, use Firebase Auth SDK directly.
    This endpoint is for admin user creation.
    """
    try:
        user = auth.create_user(
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.display_name,
        )
        return UserResponse(
            uid=user.uid,
            email=user.email or "",
            display_name=user.display_name,
            email_verified=user.email_verified,
        )
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{uid}")
async def delete_user(
    uid: str,
    current_user: TokenData = Depends(verify_firebase_token),
):
    """Delete a user (admin or self-delete)."""
    # Allow self-delete or admin
    if current_user.uid != uid:
        # TODO: Check admin role
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        auth.delete_user(uid)
        return {"message": "User deleted"}
    except auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

@router.post("/users/{uid}/verify-email")
async def send_verification_email(uid: str):
    """Generate email verification link (send via your email service)."""
    try:
        link = auth.generate_email_verification_link(uid)
        # TODO: Send via email service
        return {"message": "Verification email sent", "link": link}
    except auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
```

### Step 5: Frontend Implementation (React)

**firebase.ts:**
```typescript
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  GoogleAuthProvider,
  signInWithPopup,
  sendEmailVerification,
  User
} from 'firebase/auth';

// Fetch config from backend (or use env vars)
let firebaseConfig: any = null;
let auth: any = null;

export async function initializeFirebase() {
  if (auth) return auth;

  // Get config from backend to ensure API key is current
  const response = await fetch('/api/auth/config');
  firebaseConfig = await response.json();

  const app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  return auth;
}

export async function signIn(email: string, password: string) {
  const auth = await initializeFirebase();
  const result = await signInWithEmailAndPassword(auth, email, password);
  return result.user;
}

export async function signUp(email: string, password: string) {
  const auth = await initializeFirebase();
  const result = await createUserWithEmailAndPassword(auth, email, password);

  // Send verification email
  await sendEmailVerification(result.user);

  return result.user;
}

export async function signInWithGoogle() {
  const auth = await initializeFirebase();
  const provider = new GoogleAuthProvider();
  const result = await signInWithPopup(auth, provider);
  return result.user;
}

export async function logout() {
  const auth = await initializeFirebase();
  await signOut(auth);
}

export async function getIdToken(): Promise<string | null> {
  const auth = await initializeFirebase();
  const user = auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

// Hook for React
export function useAuth(callback: (user: User | null) => void) {
  initializeFirebase().then(auth => {
    onAuthStateChanged(auth, callback);
  });
}
```

**api-client.ts:**
```typescript
import { getIdToken } from './firebase';

export async function apiRequest(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = await getIdToken();

  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  headers.set('Content-Type', 'application/json');

  return fetch(`/api${path}`, {
    ...options,
    headers,
  });
}

// Usage:
// const response = await apiRequest('/users/me');
// const user = await response.json();
```

## Advanced

### Custom Claims for Role-Based Access

**Setting claims (backend):**
```python
def set_user_role(uid: str, role: str) -> None:
    """Set custom claims for role-based access."""
    auth.set_custom_user_claims(uid, {"role": role})

# Usage
set_user_role("user123", "admin")
```

**Checking claims (backend):**
```python
class RequireRole:
    """Dependency that requires a specific role."""

    def __init__(self, role: str):
        self.role = role

    async def __call__(
        self,
        authorization: Annotated[str | None, Header()] = None
    ) -> TokenData:
        user = await verify_firebase_token(authorization)

        # Re-verify to get claims (or cache)
        try:
            decoded = auth.verify_id_token(authorization[7:])
            user_role = decoded.get("role")
            if user_role != self.role:
                raise HTTPException(
                    status_code=403,
                    detail=f"Requires {self.role} role"
                )
        except Exception:
            raise HTTPException(status_code=403, detail="Access denied")

        return user

require_admin = RequireRole("admin")

# Usage
@app.delete("/admin/users/{uid}")
async def admin_delete_user(
    uid: str,
    admin: TokenData = Depends(require_admin)
):
    auth.delete_user(uid)
```

### Codespace Secrets Setup

**1. Add secrets to repository:**
```bash
# Via GitHub CLI
gh secret set GOOGLE_APPLICATION_CREDENTIALS_JSON < service-account.json
gh secret set GCP_API_KEY --body "AIza..."
gh secret set GCP_PROJECT_ID --body "my-project-id"
```

**2. Configure devcontainer.json:**
```json
{
  "secrets": {
    "GOOGLE_APPLICATION_CREDENTIALS_JSON": {
      "description": "GCP service account JSON for Firebase Admin"
    },
    "GCP_API_KEY": {
      "description": "GCP API key for Firebase Auth (restricted)"
    },
    "GCP_PROJECT_ID": {
      "description": "GCP project ID"
    }
  }
}
```

**3. Map secrets in post-start.sh:**
```bash
#!/bin/bash
# Map Codespace secrets to app env vars
if [ -n "$CODESPACE_NAME" ]; then
    # Write service account to file
    if [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON" ]; then
        echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/gcp-credentials.json
        export GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcp-credentials.json"
    fi
fi
```

### Multi-Tenant Authentication

```python
from firebase_admin import tenant_mgt

# Create tenant
tenant = tenant_mgt.create_tenant(
    display_name="Acme Corp",
    enable_email_link_sign_in=True,
    enable_password_sign_in=True,
)

# Verify token for specific tenant
def verify_tenant_token(token: str, tenant_id: str) -> dict:
    decoded = auth.verify_id_token(token)
    if decoded.get("firebase", {}).get("tenant") != tenant_id:
        raise ValueError("Token not for this tenant")
    return decoded
```

### Session Management

```python
from firebase_admin import auth
from datetime import timedelta

def create_session_cookie(id_token: str, expires_in: timedelta) -> str:
    """Create a session cookie from ID token."""
    return auth.create_session_cookie(
        id_token,
        expires_in=expires_in,
    )

def verify_session_cookie(cookie: str) -> dict:
    """Verify session cookie and return claims."""
    return auth.verify_session_cookie(cookie)

# FastAPI middleware for session cookies
@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_cookie = request.cookies.get("session")
    if session_cookie:
        try:
            claims = verify_session_cookie(session_cookie)
            request.state.user = claims
        except:
            pass
    return await call_next(request)
```

## Resources

- [GCP Identity Platform Docs](https://cloud.google.com/identity-platform/docs)
- [Firebase Admin Python SDK](https://firebase.google.com/docs/admin/setup)
- [Firebase Web SDK](https://firebase.google.com/docs/web/setup)
- [API Key Best Practices](https://cloud.google.com/docs/authentication/api-keys)
