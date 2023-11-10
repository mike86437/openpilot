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
            <div style="padding: 5px; color: red; font-weight: bold;" align="center">{{msg}}</div>
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

            // Check if the place has address components
            if (place.address_components) {
                // Iterate through address components to construct the full address
                var fullAddress = '';
                for (var i = 0; i < place.address_components.length; i++) {
                    var component = place.address_components[i];
                    // Concatenate the long_name of each component to the full address
                    fullAddress += component.long_name + ' ';
                }

                // Trim any extra white spaces
                fullAddress = fullAddress.trim();

                // Set the value of the input field to the full address
                document.getElementById('pac-input').value = fullAddress;
            }
        }
    </script>

