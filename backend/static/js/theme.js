(() => {
    "use strict";

    const STORAGE_KEY = "cineverse-theme";
    const THEMES = ["dark", "light"];
    const root = document.documentElement;

    function systemPreference() {
        return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
            ? "light"
            : "dark";
    }

    function getStoredTheme() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            return THEMES.includes(stored) ? stored : null;
        } catch (err) {
            // localStorage may be unavailable (privacy mode, etc) — fail quietly
            return null;
        }
    }

    function setStoredTheme(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (err) {
            // ignore write failures
        }
    }

    function paint(theme) {
        root.setAttribute("data-theme", theme);
        document.body?.setAttribute("data-theme", theme);

        THEMES.forEach((t) => {
            root.classList.toggle(`theme-${t}`, t === theme);
            document.body?.classList.toggle(`theme-${t}`, t === theme);
        });

        // let any listening UI (toggle buttons, icons) react
        window.dispatchEvent(
            new CustomEvent("cineverse:theme-change", { detail: { theme } })
        );
    }

    function applyTheme(theme) {
        const next = THEMES.includes(theme) ? theme : getStoredTheme() || systemPreference();
        paint(next);
        setStoredTheme(next);
        return next;
    }

    function currentTheme() {
        return root.getAttribute("data-theme") || getStoredTheme() || systemPreference();
    }

    function toggleTheme() {
        const next = currentTheme() === "dark" ? "light" : "dark";
        return applyTheme(next);
    }

    window.CineVerseTheme = {
        apply: applyTheme,
        current: currentTheme,
        toggle: toggleTheme
    };

    // Apply as early as possible to avoid a flash of the wrong theme
    applyTheme(getStoredTheme() || systemPreference());

    document.addEventListener("DOMContentLoaded", () => {
        // Re-affirm once the DOM (and body) exists, and wire up any toggle buttons
        applyTheme(currentTheme());

        document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
            btn.setAttribute("aria-pressed", currentTheme() === "dark");
            btn.addEventListener("click", () => {
                const theme = toggleTheme();
                btn.setAttribute("aria-pressed", theme === "dark");
            });
        });
    });

    // Follow the OS theme change only if the user hasn't picked one explicitly
    window.matchMedia?.("(prefers-color-scheme: light)").addEventListener("change", (e) => {
        if (!getStoredTheme()) {
            applyTheme(e.matches ? "light" : "dark");
        }
    });
})();