document.querySelectorAll(".js-validate").forEach((form) => {
    form.querySelectorAll("input, select, textarea").forEach((field) => {
        field.addEventListener("invalid", () => {
            field.style.transform = "translateY(-1px)";
        });
        field.addEventListener("input", () => {
            field.style.transform = "translateY(0)";
        });
    });
});

document.querySelectorAll("[data-back-button]").forEach((link) => {
    link.addEventListener("click", (event) => {
        if (window.history.length > 1 && document.referrer) {
            event.preventDefault();
            window.history.back();
        }
    });
});
