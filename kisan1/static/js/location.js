function fetchLocationDetails() {
    const pincodeInput = (document.getElementById('pincode')?.value || '').trim();
    const districtInput = document.getElementById('district');
    const mandalInput = document.getElementById('mandal');
    const villageSelect = document.getElementById('village');

    if (!districtInput || !mandalInput || !villageSelect) {
        return;
    }

    districtInput.value = '';
    mandalInput.value = '';
    villageSelect.innerHTML = '<option value="" disabled selected>-- Enter Pincode First --</option>';

    if (!/^\d{6}$/.test(pincodeInput)) {
        return;
    }

    villageSelect.innerHTML = '<option value="" disabled selected>Loading data...</option>';

    fetch(`/get-location/?pincode=${encodeURIComponent(pincodeInput)}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Request failed (${response.status})`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                districtInput.value = data.district || '';
                mandalInput.value = data.mandal || '';

                villageSelect.innerHTML = '<option value="" disabled selected>-- Select Village --</option>';
                (data.villages || []).forEach(village => {
                    const option = document.createElement('option');
                    option.value = village;
                    option.text = village;
                    villageSelect.appendChild(option);
                });
                if ((data.villages || []).length === 0) {
                    villageSelect.innerHTML = '<option value="" disabled selected>No villages found</option>';
                }
            } else {
                villageSelect.innerHTML = '<option value="" disabled selected>Pincode not found in database</option>';
            }
        })
        .catch(error => {
            console.error('Error fetching location:', error);
            villageSelect.innerHTML = '<option value="" disabled selected>Location unavailable. Try again.</option>';
        });
}
