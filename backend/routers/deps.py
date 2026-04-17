"""
Shared FastAPI dependencies for commodity name normalization.

The backend's internal name for the soybean commodity is ``soybean`` (singular)
— it is stored that way in ``futures_daily``, ``price_forecasts``, and the
training code. The web frontend uses ``soybeans`` (plural) in
``CROP_COMMODITIES`` and throughout its pill UI. Rather than force either side
to switch, the normalizer here accepts both and canonicalizes to the internal
form before the route handler sees it.

Use by declaring the query parameter as a Depends on the appropriate helper:

    from fastapi import Depends
    from .deps import commodity_param, crop_param

    @router.get("/foo")
    async def handler(commodity: str = Depends(commodity_param)):
        ...
"""

from fastapi import Query

# Accepts corn / soybean / soybeans / wheat; normalizes plural → singular so
# that the DB queries, which store ``soybean``, always match.
_CROP_PATTERN = r"^(corn|soybeans?|wheat)$"


def commodity_param(
    commodity: str = Query(..., pattern=_CROP_PATTERN),
) -> str:
    """Query-string commodity with ``soybeans`` plural normalization."""
    return "soybean" if commodity == "soybeans" else commodity


def crop_param(
    crop: str = Query(..., pattern=_CROP_PATTERN),
) -> str:
    """Same normalizer, parameter name ``crop`` for yield endpoints."""
    return "soybean" if crop == "soybeans" else crop
