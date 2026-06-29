(function () {
    "use strict";

    const allowedThemes = ["white", "dark"];
    const storageKey = "cineverse-theme";
    const defaultTheme = "white";

    function normalizeTheme(theme) {
        return allowedThemes.includes(theme) ? theme : defaultTheme;
    }

    function getSavedTheme() {
        return normalizeTheme(localStorage.getItem(storageKey));
    }

    function applyTheme(theme) {
        const selectedTheme = normalizeTheme(theme);

        document.documentElement.setAttribute("data-theme", selectedTheme);
        document.body.setAttribute("data-theme", selectedTheme);

        document.body.classList.toggle("theme-dark", selectedTheme === "dark");
        document.body.classList.toggle("theme-white", selectedTheme === "white");

        localStorage.setItem(storageKey, selectedTheme);

        document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
            const isActive = button.getAttribute("data-theme-choice") === selectedTheme;

            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
    }

    function bindThemeButtons() {
        document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
            button.addEventListener("click", function () {
                const theme = button.getAttribute("data-theme-choice");
                applyTheme(theme);
            });
        });
    }

    window.CineVerseTheme = {
        apply: applyTheme,
        current: getSavedTheme
    };

    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(getSavedTheme());
        bindThemeButtons();
    });
}());