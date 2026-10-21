"""Stealth Driver Injection & Anti-Bot Armor.

Injects JavaScript shims and prototypes before any page scripts execute, eliminating
automation artifacts (such as `navigator.webdriver`), providing realistic `window.chrome`,
plugins, permissions, and WebGL parameters to prevent Cloudflare, Turnstile, and
Datadome bot detection traps.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from .fingerprint import BrowserProfile

logger = logging.getLogger("smart_miner.crawler.stealth")

STEALTH_JS_TEMPLATE = """
(() => {
    // 1. Wipe navigator.webdriver
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        if (navigator.__proto__) {
            delete navigator.__proto__.webdriver;
        }
    } catch (e) {}

    // 2. Mock window.chrome
    try {
        if (!window.chrome) {
            window.chrome = {
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                },
                runtime: {
                    OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                    PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                    connect: function() {},
                    sendMessage: function() {}
                },
                csi: function() {},
                loadTimes: function() {}
            };
        }
    } catch (e) {}

    // 3. Mock languages
    try {
        const customLanguages = __LANGUAGES__;
        Object.defineProperty(navigator, 'languages', {
            get: () => customLanguages,
            configurable: true
        });
    } catch (e) {}

    // 4. Mock navigator.plugins and mimeTypes
    try {
        function makePlugin(name, description, filename) {
            return {
                name: name,
                description: description,
                filename: filename,
                length: 1,
                item: function(index) { return this[index] || null; },
                namedItem: function(n) { return (n === this.name) ? this : null; }
            };
        }

        const plugins = [
            makePlugin('PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer'),
            makePlugin('Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer'),
            makePlugin('Chromium PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer')
        ];

        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (n) => plugins.find(p => p.name === n) || null;
                plugins.refresh = () => {};
                return plugins;
            },
            configurable: true
        });
    } catch (e) {}

    // 5. Mock Notification Permissions
    try {
        if (window.navigator && window.navigator.permissions) {
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => {
                if (params && params.name === 'notifications') {
                    return Promise.resolve({
                        state: 'prompt',
                        onchange: null,
                        addEventListener: function() {},
                        removeEventListener: function() {},
                        dispatchEvent: function() { return false; }
                    });
                }
                return origQuery ? origQuery.apply(window.navigator.permissions, [params]) : Promise.resolve({ state: 'denied' });
            };
        }
    } catch (e) {}

    // 6. Mock WebGL Vendor & Renderer
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) return 'Intel Inc.';
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.apply(this, [parameter]);
        };
        if (window.WebGL2RenderingContext) {
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter2.apply(this, [parameter]);
            };
        }
    } catch (e) {}
})();
"""


@dataclass
class StealthConfig:
    """Options for stealth code generation."""

    languages: List[str] | None = None
    mock_webgl: bool = True
    mock_chrome_runtime: bool = True
    mask_webdriver: bool = True


class StealthEngine:
    """Generates and injects stealth payloads into Playwright browser instances."""

    def __init__(self, config: StealthConfig | None = None):
        self.config = config or StealthConfig()

    def build_init_script(self, profile: BrowserProfile | None = None) -> str:
        """Render self-contained JS string with configuration parameters."""
        langs = self.config.languages
        if not langs:
            accept_lang = None
            if profile and hasattr(profile, "headers") and profile.headers:
                accept_lang = profile.headers.get("Accept-Language") or profile.headers.get("accept-language")
            if accept_lang:
                parts = [p.split(";")[0].strip() for p in accept_lang.split(",") if p.strip()]
                langs = parts if parts else ["en-US", "en"]
            else:
                langs = ["en-US", "en"]

        script = STEALTH_JS_TEMPLATE.replace("__LANGUAGES__", json.dumps(langs))
        return script

    async def apply_to_context(
        self, context: Any, profile: BrowserProfile | None = None
    ) -> None:
        """Inject init script into all current and future pages in a BrowserContext."""
        script = self.build_init_script(profile)
        if hasattr(context, "add_init_script"):
            await context.add_init_script(script)

    async def apply_to_page(
        self, page: Any, profile: BrowserProfile | None = None
    ) -> None:
        """Inject init script into an individual Page."""
        script = self.build_init_script(profile)
        if hasattr(page, "add_init_script"):
            await page.add_init_script(script)
