"""Agente Chrome — navegación headless con Playwright sobre dominios autorizados."""
import asyncio
import base64
import logging
from dataclasses import dataclass, field

from .security import ChromeSecurityChecker

logger = logging.getLogger(__name__)

# Señales de que el sitio requiere login (comunes en Instagram y LinkedIn)
_LOGIN_SIGNALS = [
    "log in", "sign in", "iniciar sesión", "inicia sesión",
    "create an account", "join now", "join linkedin",
    "you must be logged in", "this content isn't available",
    "login required",
]

# User-agent genérico de Chrome moderno
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class NavigationResult:
    url: str
    title: str
    text_content: str
    screenshot_b64: str | None = None
    flagged: bool = False
    flag_reason: str | None = None
    needs_login: bool = False
    error: str | None = None
    meta: dict = field(default_factory=dict)


class ChromeAgent:
    """
    Navegador headless con lista blanca de dominios y detección de injection.
    Una instancia por request — no mantiene estado entre llamadas.
    """

    def __init__(self) -> None:
        self._checker = ChromeSecurityChecker()

    async def navigate(
        self,
        url: str,
        take_screenshot: bool = False,
        wait_until: str = "networkidle",
    ) -> NavigationResult:
        # 1. Validar dominio antes de abrir cualquier conexión
        domain_check = self._checker.check_domain(url)
        if not domain_check.allowed:
            return NavigationResult(
                url=url, title="", text_content="",
                flagged=True, flag_reason=domain_check.reason,
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return NavigationResult(
                url=url, title="", text_content="",
                error="Playwright no está instalado. Ejecutá: pip install playwright && playwright install chromium",
            )

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = await browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )
            page = await context.new_page()

            # Bloquear recursos innecesarios para acelerar carga
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
                lambda route: route.abort(),
            )

            try:
                await page.goto(url, wait_until=wait_until, timeout=30_000)
            except Exception as exc:
                await browser.close()
                return NavigationResult(url=url, title="", text_content="", error=str(exc))

            title = await page.title()

            # 2. Detectar texto oculto y chequearlo
            hidden_text: str = await page.evaluate("""
                () => {
                    const parts = [];
                    for (const el of document.querySelectorAll('*')) {
                        const s = window.getComputedStyle(el);
                        const text = el.textContent?.trim() || '';
                        if (!text) continue;
                        if (
                            s.display === 'none' ||
                            s.visibility === 'hidden' ||
                            parseFloat(s.opacity) === 0 ||
                            parseFloat(s.fontSize) < 2
                        ) {
                            parts.push(text.slice(0, 200));
                        }
                    }
                    return parts.join(' ');
                }
            """)

            if hidden_text:
                injection_check = self._checker.check_injection(hidden_text)
                if injection_check.flagged:
                    screenshot_b64 = None
                    if take_screenshot:
                        screenshot_b64 = base64.b64encode(await page.screenshot()).decode()
                    await browser.close()
                    return NavigationResult(
                        url=url, title=title, text_content="",
                        screenshot_b64=screenshot_b64,
                        flagged=True,
                        flag_reason=f"Texto oculto sospechoso en la página. {injection_check.reason}",
                    )

            # 3. Extraer texto visible (sin scripts/styles)
            visible_text: str = await page.evaluate("""
                () => {
                    const clone = document.body?.cloneNode(true);
                    if (!clone) return '';
                    clone.querySelectorAll('script,style,noscript,svg').forEach(n => n.remove());
                    return (clone.innerText || clone.textContent || '').replace(/\\s+/g, ' ').trim();
                }
            """)

            # Limitar a 6000 chars para no saturar el contexto del modelo
            visible_text = visible_text[:6000]

            # 4. Chequear injection en texto visible
            text_check = self._checker.check_injection(visible_text)
            if text_check.flagged:
                await browser.close()
                return NavigationResult(
                    url=url, title=title,
                    text_content="[CONTENIDO BLOQUEADO — posible prompt injection detectada]",
                    flagged=True, flag_reason=text_check.reason,
                )

            # 5. Detectar si el sitio pide login
            lower_text = visible_text.lower()
            needs_login = any(signal in lower_text for signal in _LOGIN_SIGNALS)

            # 6. Screenshot opcional
            screenshot_b64 = None
            if take_screenshot:
                screenshot_b64 = base64.b64encode(await page.screenshot()).decode()

            await browser.close()
            return NavigationResult(
                url=url,
                title=title,
                text_content=visible_text,
                screenshot_b64=screenshot_b64,
                needs_login=needs_login,
                meta={"chars": len(visible_text), "hidden_chars": len(hidden_text)},
            )

    async def screenshot(self, url: str) -> NavigationResult:
        """Captura pantalla de una URL sin devolver texto."""
        return await self.navigate(url, take_screenshot=True, wait_until="load")
