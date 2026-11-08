from fastapi import APIRouter

from routes.auth_mfa_setup import router as setup_router
from routes.auth_mfa_verify import router as verify_router

router = APIRouter()
router.include_router(setup_router)
router.include_router(verify_router)
