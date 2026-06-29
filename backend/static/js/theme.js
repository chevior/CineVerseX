(function () {
    const allowedThemes = ["white", "dark"];
    const storageKey = "cineverse-theme";

    function normalizeTheme(theme) {
        return allowedThemes.includes(theme) ? theme : "white";
    }

    function applyTheme(theme) {
        const selectedTheme = normalizeTheme(theme);
        document.body.dataset.theme = selectedTheme;
        document.body.classList.toggle("theme-dark", selectedTheme === "dark");
        document.body.classList.toggle("theme-white", selectedTheme === "white");
        localStorage.setItem(storageKey, selectedTheme);

        document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
            button.classList.toggle(
                "is-active",
                button.dataset.themeChoice === selectedTheme
            );
        });
    }

    window.CineVerseTheme = {
        apply: applyTheme,
        current: function () {
            return normalizeTheme(localStorage.getItem(storageKey));
        }
    };

    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(localStorage.getItem(storageKey));

        document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
            button.addEventListener("click", function () {
                applyTheme(button.dataset.themeChoice);
            });
        });
    });
}());
