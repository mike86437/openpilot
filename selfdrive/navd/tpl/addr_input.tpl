<form name="searchForm" onsubmit="submitForm(event)">
    <fieldset class="uk-fieldset">
        <div class="uk-margin">
            <select class="uk-select" name="fav_val">
                <option value="favorites">Select Saved Destinations</option>
                <option value="home">Home</option>
                <option value="work">Work</option>
                <option value="fav1">Favorite 1</option>
                <option value="fav2">Favorite 2</option>
                <option value="fav3">Favorite 3</option>
            </select>
            <div style="padding: 5px; color: red; font-weight: bold;" align="center">{{msg}}</div>
            <input class="uk-input" type="text" name="addr_val" placeholder="Search a place">
            <input class="uk-button uk-button-primary uk-width-1-1 uk-margin-small-bottom" type="submit" value="Search">
        </div>
    </fieldset>
</form>
<script>
    async function submitForm(event) {
        event.preventDefault(); // Prevent the default form submission

        const form = document.forms['searchForm'];
        const formData = new FormData(form);

        try {
            const response = await fetch('/confirm_destination_ajax', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(Object.fromEntries(formData.entries())),
            });

            if (response.ok) {
                // Handle the response if needed
                const result = await response.json();
                console.log(result);
            } else {
                // Handle error response
                console.error('Error:', response.statusText);
            }
        } catch (error) {
            console.error('Fetch error:', error);
        }
    }
</script>
