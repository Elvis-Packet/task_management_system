function updateClock(){

    const now = new Date();

    const options = {

        weekday:'long',

        year:'numeric',

        month:'long',

        day:'numeric'

    };

    document.getElementById("liveDate").innerHTML =

        now.toLocaleDateString(undefined, options);

    document.getElementById("liveClock").innerHTML =

        now.toLocaleTimeString();

}

setInterval(updateClock,1000);

updateClock();