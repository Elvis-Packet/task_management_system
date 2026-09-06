/* Live clock for the navbar */

(function () {

    "use strict";

    var dateEl  = document.getElementById("liveDate");
    var clockEl = document.getElementById("liveClock");

    if (!dateEl || !clockEl) {
        return;
    }

    function tick() {

        var now = new Date();

        dateEl.textContent = now.toLocaleDateString(undefined, {
            weekday: "short", day: "2-digit", month: "short", year: "numeric"
        });

        clockEl.textContent = now.toLocaleTimeString(undefined, {
            hour: "2-digit", minute: "2-digit", second: "2-digit"
        });
    }

    tick();
    setInterval(tick, 1000);

})();
