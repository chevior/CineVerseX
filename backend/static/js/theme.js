(() => {
    "use strict";

    function applyTheme() {
        document.documentElement.setAttribute("data-theme", "dark");
        document.body.setAttribute("data-theme", "dark");
        document.documentElement.classList.add("theme-dark");
        document.body.classList.add("theme-dark");
    }

    window.CineVerseTheme = {
        apply: applyTheme,
        current() {
            return "dark";
        },
        toggle: applyTheme
    };

    document.addEventListener("DOMContentLoaded", () => {
        applyTheme();
    });

})();
