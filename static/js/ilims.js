/* ═══════════════════════════════════════════════════════════════
   ILIMS — Minimal progressive-enhancement JS
   ═══════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    function initAutoDismiss(root) {
        var msgs = (root || document).querySelectorAll(".message[data-auto-dismiss]:not([data-dismissed])");
        for (var i = 0; i < msgs.length; i++) {
            (function (el) {
                el.setAttribute("data-dismissed", "1");
                setTimeout(function () {
                    el.style.transition = "opacity 0.3s ease";
                    el.style.opacity = "0";
                    setTimeout(function () { el.remove(); }, 300);
                }, 6000);
            })(msgs[i]);
        }
    }

    function setupSidebar() {
        var toggle = document.getElementById("sidebar-toggle");
        var sidebar = document.getElementById("sidebar");
        var overlay = document.getElementById("sidebar-overlay");
        if (!toggle || !sidebar) return;
        toggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
            if (overlay) overlay.classList.toggle("active");
        });
        if (overlay) overlay.addEventListener("click", function () {
            sidebar.classList.remove("open");
            overlay.classList.remove("active");
        });
    }

    function initSmartSelects(root) {
        var wrappers = (root || document).querySelectorAll(".smart-select:not([data-init])");
        for (var i = 0; i < wrappers.length; i++) {
            (function (wrap) {
                wrap.setAttribute("data-init", "1");
                var inputId = wrap.getAttribute("data-input-id");
                var hidden = document.getElementById(inputId);
                var text = document.getElementById(inputId + "__text");
                var results = document.getElementById(inputId + "__results");
                if (!hidden || !text || !results) return;

                results.addEventListener("click", function (e) {
                    var li = e.target.closest(".smart-select__item");
                    if (!li) return;
                    hidden.value = li.getAttribute("data-pk");
                    text.value = li.getAttribute("data-display");
                    results.innerHTML = "";
                    text.setAttribute("aria-expanded", "false");
                    // Trigger change event so other scripts (like inline client creation) can react
                    hidden.dispatchEvent(new Event("change", { bubbles: true })); 
                });

                text.addEventListener("keydown", function (e) {
                    var items = results.querySelectorAll(".smart-select__item");
                    if (!items.length) return;
                    var active = results.querySelector(".smart-select__item.active");
                    var idx = active ? Array.prototype.indexOf.call(items, active) : -1;

                    if (e.key === "ArrowDown") {
                        e.preventDefault(); idx = Math.min(idx + 1, items.length - 1);
                    } else if (e.key === "ArrowUp") {
                        e.preventDefault(); idx = Math.max(idx - 1, 0);
                    } else if (e.key === "Enter" && active) {
                        e.preventDefault();
                        hidden.value = active.getAttribute("data-pk");
                        text.value = active.getAttribute("data-display");
                        results.innerHTML = "";
                        hidden.dispatchEvent(new Event("change", { bubbles: true }));
                        return;
                    } else if (e.key === "Escape") {
                        results.innerHTML = "";
                        return;
                    } else {
                        // Clear hidden PK if user starts typing something new
                        hidden.value = "";
                        hidden.dispatchEvent(new Event("change", { bubbles: true }));
                        return;
                    }
                    for (var j = 0; j < items.length; j++) items[j].classList.remove("active");
                    items[idx].classList.add("active");
                    items[idx].scrollIntoView({ block: "nearest" });
                });

                document.addEventListener("click", function (e) {
                    if (!wrap.contains(e.target)) results.innerHTML = "";
                });
            })(wrappers[i]);
        }
    }

    function initModals(root) {
        var overlay = (root || document).querySelector("#modal-host .modal-overlay");
        if (!overlay) return;
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay && overlay.getAttribute("data-close-on-backdrop") === "1") {
                document.getElementById("modal-host").innerHTML = "";
            }
        });
    }

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            var host = document.getElementById("modal-host");
            if (host && host.innerHTML.trim()) host.innerHTML = "";
        }
    });

    // TELL HTMX TO RENDER 400 ERRORS SO WE CAN SEE FORM VALIDATION
    // Show 400 validation responses inside the modal (don't treat as hard error)
document.body.addEventListener("htmx:beforeSwap", function (evt) {
    var status = evt.detail.xhr.status;
    if (status === 400 || status === 422) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
    }
});

// In development: any 500 becomes a visible red toast, never silent
document.body.addEventListener("htmx:responseError", function (evt) {
    var status = evt.detail.xhr.status;
    var host = document.getElementById("toast-host");
    if (!host) return;
    var div = document.createElement("div");
    div.className = "message message--error";
    div.setAttribute("role", "alert");
    div.setAttribute("data-auto-dismiss", "1");
    div.innerHTML = "<span><strong>Server error " + status + ":</strong> "
        + "Request failed. Check the form values or server log. "
        + "(Development mode — error is not hidden.)</span>";
    host.appendChild(div);
});

document.body.addEventListener("htmx:sendError", function () {
    var host = document.getElementById("toast-host");
    if (!host) return;
    var div = document.createElement("div");
    div.className = "message message--error";
    div.setAttribute("role", "alert");
    div.innerHTML = "<span><strong>Network error:</strong> Could not reach the server.</span>";
    host.appendChild(div);
}); 

    document.addEventListener("htmx:configRequest", function (e) {
        var csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
        if (csrfInput) e.detail.headers["X-CSRFToken"] = csrfInput.value;
    });

    document.addEventListener("htmx:afterSwap", function (e) {
        initAutoDismiss(document);
        initSmartSelects(document);
        initModals(document);
    });

    

    document.body.addEventListener("htmx:beforeSwap", function (evt) {
    if (evt.detail.xhr.status === 400 || evt.detail.xhr.status === 422) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
    }
});

    function init() {
        initAutoDismiss(document);
        setupSidebar();
        initSmartSelects(document);
        initModals(document);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();