from routes.auth import router as auth_router
from routes.auth_mfa import router as auth_mfa_router
from routes.users import router as users_router
from routes.admins import router as admins_router
from routes.questions import router as questions_router
from routes.health import router as health_router
from routes.stats import router as stats_router
from routes.management import router as management_router
from routes.bot import router as bot_router
from routes.monitoring import router as monitoring_router
from routes.consent import router as consent_router
from routes.knowledge import router as knowledge_router
from routes.service_miss import admin_router as service_misses_admin_router, bot_router as service_misses_bot_router
from routes.health_fact import router as health_facts_router

__all__ = [
    "auth_router",
    "auth_mfa_router",
    "users_router",
    "admins_router",
    "questions_router",
    "health_router",
    "stats_router",
    "management_router",
    "bot_router",
    "monitoring_router",
    "consent_router",
    "knowledge_router",
    "service_misses_bot_router",
    "service_misses_admin_router",
    "health_facts_router",
]
