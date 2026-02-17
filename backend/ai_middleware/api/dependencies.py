"""FastAPI dependencies for API routes."""

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from backend.ai_middleware.config import Settings, get_settings
from backend.ai_middleware.providers.registry import ProviderRegistry, get_registry


async def get_settings_dep() -> Settings:
    """Dependency to get application settings."""
    return get_settings()


async def get_registry_dep() -> ProviderRegistry:
    """Dependency to get the provider registry."""
    return get_registry()


async def verify_api_key(
    x_api_key: Annotated[Optional[str], Header()] = None,
    authorization: Annotated[Optional[str], Header()] = None,
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """
    Verify the API key from headers.
    
    Accepts either X-API-Key header or Authorization: Bearer <token> header.
    """
    api_key = x_api_key
    
    if not api_key and authorization:
        # Extract from Bearer token
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            api_key = parts[1]
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header or Authorization: Bearer <token>",
        )
    
    # In production, validate against stored API keys
    # For now, just return the key
    return api_key


async def get_provider_name(
    provider: Optional[str] = None,
    x_provider: Annotated[Optional[str], Header()] = None,
) -> Optional[str]:
    """Get provider name from query param or header."""
    return provider or x_provider


# Type aliases for dependency injection
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry_dep)]
ApiKeyDep = Annotated[str, Depends(verify_api_key)]
ProviderDep = Annotated[Optional[str], Depends(get_provider_name)]

