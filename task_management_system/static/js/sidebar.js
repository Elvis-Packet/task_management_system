const sidebar = document.getElementById("sidebar");

const toggle = document.getElementById("sidebarToggle");

toggle.addEventListener("click",()=>{

    sidebar.classList.toggle("collapsed");

});