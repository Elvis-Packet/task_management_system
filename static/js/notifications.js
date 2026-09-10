/* ==========================================================
   TPMS NOTIFICATIONS
   Navbar dropdown behaviour
========================================================== */

(function () {

    "use strict";

    var toggle   = document.getElementById("notificationToggle");
    var dropdown = document.getElementById("notificationDropdown");
    var badge    = document.getElementById("notificationCount");
    var markAll  = document.getElementById("markAllRead");

    if (!toggle || !dropdown) {
        return;
    }

    // ------------------------------------------------------
    // CSRF-free POST helper (session cookie auth)
    // ------------------------------------------------------

    function post(url) {

        return fetch(url, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json"
            },
            credentials: "same-origin"
        }).then(function (response) {

            if (!response.ok) {
                throw new Error("Request failed: " + response.status);
            }

            return response.json();
        });
    }

    // ------------------------------------------------------
    // Badge
    // ------------------------------------------------------

    function setBadge(count) {

        if (!badge) {
            return;
        }

        if (count > 0) {
            badge.textContent = count > 9 ? "9+" : count;
            badge.style.display = "flex";
        } else {
            badge.style.display = "none";
        }

        if (markAll) {
            markAll.style.display = count > 0 ? "inline-block" : "none";
        }
    }

    // ------------------------------------------------------
    // Open / close
    // ------------------------------------------------------

    function closeDropdown() {
        dropdown.classList.remove("show");
        toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function (event) {

        event.stopPropagation();

        var isOpen = dropdown.classList.toggle("show");

        toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    // Clicks inside the panel must not bubble up and close it
    dropdown.addEventListener("click", function (event) {
        event.stopPropagation();
    });

    document.addEventListener("click", function () {
        closeDropdown();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeDropdown();
        }
    });

    // ------------------------------------------------------
    // Mark all as read
    // ------------------------------------------------------

    if (markAll) {

        markAll.addEventListener("click", function (event) {

            event.preventDefault();
            event.stopPropagation();

            post("/notifications/read-all")
                .then(function (data) {

                    document
                        .querySelectorAll(".notification-item.unread")
                        .forEach(function (item) {
                            item.classList.remove("unread");
                        });

                    setBadge(data.count || 0);
                })
                .catch(function (error) {
                    console.error("[TPMS] mark all read failed", error);
                });
        });
    }

    // ------------------------------------------------------
    // Mark one as read
    //
    // The item is a real link to /notifications/<id>/open, which
    // marks it read server-side and redirects. We only optimistically
    // update the badge so the UI reacts before navigation.
    // ------------------------------------------------------

    document
        .querySelectorAll(".notification-item[data-notification-id]")
        .forEach(function (item) {

            item.addEventListener("click", function () {

                if (!item.classList.contains("unread")) {
                    return;
                }

                item.classList.remove("unread");

                var current = parseInt(badge && badge.textContent, 10);

                if (!isNaN(current)) {
                    setBadge(current - 1);
                }
            });
        });

    // ------------------------------------------------------
    // Poll the unread count
    // ------------------------------------------------------

    function refreshCount() {

        if (document.hidden) {
            return;
        }

        fetch("/notifications/unread-count", {
            headers: { "Accept": "application/json" },
            credentials: "same-origin"
        })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (data) {
                if (data) {
                    setBadge(data.count);
                }
            })
            .catch(function () {
                /* offline or session expired - stay quiet */
            });
    }

    setInterval(refreshCount, 60000);

})();
