// Add event listener for vote form submission
document.addEventListener("DOMContentLoaded", function() {
    const voteForm = document.querySelector("form[action='/submit_vote']");
    if(voteForm) {
        voteForm.addEventListener("submit", function(event) {
            const selected = document.querySelector("input[name='candidate']:checked");
            if(!selected) {
                alert("Please select a candidate before submitting!");
                event.preventDefault(); // Prevent form submission
            } else {
                alert("Your vote for " + selected.value + " has been submitted!");
            }
        });
    }

    // Optional: alert on login or registration
    const loginForm = document.querySelector("form[action='/login']");
    if(loginForm) {
        loginForm.addEventListener("submit", function() {
            alert("Logging in...");
        });
    }

    const registerForm = document.querySelector("form[action='/register']");
    if(registerForm) {
        registerForm.addEventListener("submit", function() {
            alert("Registering your account...");
        });
    }
});
