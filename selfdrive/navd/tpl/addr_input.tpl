<form name="searchForm" method="post">
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
            <input class="uk-input" type="text" name="addr_val" id="pac-input" placeholder="Search a place">
            <input class="uk-button uk-button-primary uk-width-1-1 uk-margin-small-bottom" type="submit" value="Search">
        </div>
    </fieldset>
</form>


    <script src="https://maps.googleapis.com/maps/api/js?key={{gmap_key}}&libraries=places&callback=initAutocomplete" async defer></script>

    <script>
        let autocomplete;

        function initAutocomplete() {
            autocomplete = new google.maps.places.Autocomplete(
                document.getElementById('pac-input')
            );
            autocomplete.addListener('place_changed', onPlaceChanged);
        }

        function onPlaceChanged() {
    var place = autocomplete.getPlace();

    // Check if the place has a formatted address
    if (place.formatted_address) {
        // Set the value of the input field to the formatted address
        document.getElementById('pac-input').value = place.formatted_address;
    }
}
    </script>

