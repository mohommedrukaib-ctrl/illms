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
        // Backdrop click does NOT close the modal.
        // Close only via [data-close-modal] button or Escape key.
        var overlay = (root || document).querySelector("#modal-host .modal-overlay");
        if (!overlay) return;
    }

    // Escape key closes any open modal
    document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        var host = document.getElementById("modal-host");
        if (host && host.innerHTML.trim()) {
            host.innerHTML = "";
        }
    });

    /*
     * Modal Close: only when explicit [data-close-modal] is clicked
     */
    document.addEventListener("click", function (e) {
        var closeBtn = e.target.closest("[data-close-modal]");
        if (closeBtn) {
            e.preventDefault();
            var host = document.getElementById("modal-host");
            if (host) host.innerHTML = "";
            return;
        }
        var printBtn = e.target.closest("[data-action='print']");
        if (printBtn) {
            e.preventDefault();
            window.print();
        }
    });

    // Render 400 validation responses inside modal
    document.body.addEventListener("htmx:beforeSwap", function (evt) {
        var status = evt.detail.xhr.status;
        if (status === 400 || status === 422) {
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
        }
    });

    document.body.addEventListener("htmx:responseError", function (evt) {
        var status = evt.detail.xhr.status;
        var host = document.getElementById("toast-host");
        if (!host) return;
        var div = document.createElement("div");
        div.className = "message message--error";
        div.setAttribute("role", "alert");
        div.setAttribute("data-auto-dismiss", "1");
        div.innerHTML = "<span><strong>Server error " + status + ":</strong> Request failed.</span>";
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

    /*
     * Modal Close: Only closes when explicit [data-close-modal] is clicked
     */
    document.addEventListener("click", function (e) {
        var closeBtn = e.target.closest("[data-close-modal]");
        if (closeBtn) {
            e.preventDefault();
            var host = document.getElementById("modal-host");
            if (host) host.innerHTML = "";
            return;
        }
        var printBtn = e.target.closest("[data-action='print']");
        if (printBtn) {
            e.preventDefault();
            window.print();
        }
    });

    document.body.addEventListener("ilims:refresh", function () {
        window.location.reload();
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