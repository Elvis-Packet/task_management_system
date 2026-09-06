/* Sidebar collapse toggle */

(function () {

    "use strict";

    var toggle  = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("sidebar");

    if (!toggle || !sidebar) {
        return;
    }

    toggle.addEventListener("click", function () {
        sidebar.classList.toggle("collapsed");
        sidebar.classList.toggle("show");
    });

})();
