function resetSelectOptions(selectElement, placeholder, disabled = false) {
    if (!selectElement) {
        return;
    }

    selectElement.innerHTML = '';
    const option = document.createElement('option');
    option.value = '';
    option.textContent = placeholder;
    option.disabled = true;
    option.selected = true;
    selectElement.appendChild(option);
    selectElement.disabled = disabled;
}

function populateSelectOptions(selectElement, values, placeholder, selectedValue = '') {
    if (!selectElement) {
        return;
    }

    resetSelectOptions(selectElement, placeholder, false);
    values.forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        if (value === selectedValue) {
            option.selected = true;
        }
        selectElement.appendChild(option);
    });
}

function getVillagesForSelectedMandal(data, selectedMandal) {
    if (!data) {
        return [];
    }

    if (data.villages_by_mandal && selectedMandal && data.villages_by_mandal[selectedMandal]) {
        return data.villages_by_mandal[selectedMandal];
    }
    return data.villages || [];
}

function fetchLocationDetails() {
    const pincodeInput = (document.getElementById('pincode')?.value || '').trim();
    const districtInput = document.getElementById('district');
    const mandalField = document.getElementById('mandal');
    const villageSelect = document.getElementById('village');

    if (!districtInput || !mandalField || !villageSelect) {
        return;
    }

    districtInput.value = '';
    if (mandalField.tagName === 'SELECT') {
        resetSelectOptions(mandalField, '-- Select Mandal --', true);
    } else {
        mandalField.value = '';
    }
    resetSelectOptions(villageSelect, '-- Enter Pincode First --', true);

    if (!/^\d{6}$/.test(pincodeInput)) {
        return;
    }

    resetSelectOptions(villageSelect, 'Loading data...', true);

    fetch(`/get-location/?pincode=${encodeURIComponent(pincodeInput)}`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error(`Request failed (${response.status})`);
            }
            return response.json();
        })
        .then((data) => {
            if (!data.success) {
                resetSelectOptions(villageSelect, 'Pincode not found in database', true);
                if (mandalField.tagName === 'SELECT') {
                    resetSelectOptions(mandalField, '-- Select Mandal --', true);
                }
                return;
            }

            districtInput.value = data.district || '';

            if (mandalField.tagName === 'SELECT') {
                populateSelectOptions(
                    mandalField,
                    data.mandals || [],
                    '-- Select Mandal --',
                    data.mandal || '',
                );
                mandalField.disabled = false;
                mandalField.onchange = function onMandalChange() {
                    const selectedMandal = mandalField.value;
                    const villages = getVillagesForSelectedMandal(data, selectedMandal);
                    if (villages.length) {
                        populateSelectOptions(villageSelect, villages, '-- Select Village --');
                    } else {
                        resetSelectOptions(villageSelect, 'No villages found', true);
                    }
                };
            } else {
                mandalField.value = data.mandal || '';
            }

            const selectedMandal = mandalField.tagName === 'SELECT' ? mandalField.value : data.mandal;
            const villages = getVillagesForSelectedMandal(data, selectedMandal);
            if (villages.length) {
                populateSelectOptions(villageSelect, villages, '-- Select Village --');
            } else {
                resetSelectOptions(villageSelect, 'No villages found', true);
            }
        })
        .catch((error) => {
            console.error('Error fetching location:', error);
            if (mandalField.tagName === 'SELECT') {
                resetSelectOptions(mandalField, '-- Select Mandal --', true);
            }
            resetSelectOptions(villageSelect, 'Location unavailable. Try again.', true);
        });
}
