"""Provider management routes."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from backend.ai_middleware.api.dependencies import RegistryDep
from backend.ai_middleware.core.base import ProviderCapability, ProviderInfo

router = APIRouter()


@router.get("", response_model=List[ProviderInfo])
async def list_providers(
    registry: RegistryDep,
    capability: Optional[ProviderCapability] = None,
) -> List[ProviderInfo]:
    """
    List all registered providers.
    
    Optionally filter by capability.
    """
    if capability:
        return registry.find_by_capability(capability)
    return registry.list_providers()


@router.get("/{provider_name}", response_model=ProviderInfo)
async def get_provider(
    provider_name: str,
    registry: RegistryDep,
) -> ProviderInfo:
    """Get information about a specific provider."""
    if not registry.has_provider(provider_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    
    provider = registry.get(provider_name)
    return provider.provider_info


@router.get("/{provider_name}/health")
async def check_provider_health(
    provider_name: str,
    registry: RegistryDep,
) -> dict:
    """Check the health of a specific provider."""
    if not registry.has_provider(provider_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    
    provider = registry.get(provider_name)
    is_healthy = await provider.health_check()
    
    return {
        "provider": provider_name,
        "healthy": is_healthy,
        "status": "ok" if is_healthy else "unhealthy",
    }


@router.get("/capabilities/{capability}", response_model=List[ProviderInfo])
async def find_providers_by_capability(
    capability: ProviderCapability,
    registry: RegistryDep,
) -> List[ProviderInfo]:
    """Find all providers that support a specific capability."""
    return registry.find_by_capability(capability)

