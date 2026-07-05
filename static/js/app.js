// --- INVENTORY MANAGEMENT LOGIC ---
const inventoryTableBody = document.getElementById('inventoryTableBody');
const addMedicineForm = document.getElementById('addMedicineForm');
const searchInput = document.getElementById('searchInput');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageInfo = document.getElementById('pageInfo');

let currentPage = 0;
const limit = 50;
let currentSearch = '';

// API se medicines fetch karke HTML table mein dalna
async function loadMedicines() {
    if (!inventoryTableBody) return; // Yeh code sirf tab chalega jab table page par maujood ho

    try {
        const skip = currentPage * limit;
        const queryParams = new URLSearchParams({ skip, limit });
        if (currentSearch) queryParams.append('search_query', currentSearch);
        
        const response = await fetch(`/api/inventory/?${queryParams.toString()}`);
        const medicines = await response.json();

        inventoryTableBody.innerHTML = '';
        
        // Update pagination buttons state
        if (pageInfo) pageInfo.innerText = `Page ${currentPage + 1}`;
        if (prevPageBtn) prevPageBtn.disabled = (currentPage === 0);
        if (nextPageBtn) nextPageBtn.disabled = (medicines.length < limit);

        if (medicines.length === 0) {
            inventoryTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No items found.</td></tr>';
            return;
        }
        medicines.forEach(med => {
            // Agar stock 10 ya usse kam hai, toh color red (danger) ho jayega
            const stockColor = med.stock_quantity <= 10 ? 'var(--danger)' : 'var(--success)';
            
            const row = `
                <tr>
                    <td><strong>${med.barcode}</strong></td>
                    <td>
                        ${med.name} 
                        ${med.generic_name ? `<br><small style="color:#9CA3AF;">${med.generic_name}</small>` : ''}
                    </td>
                    <td>Rs. ${med.sale_price}</td>
                    <td><span style="color: ${stockColor}; font-weight: 700;">${med.stock_quantity}</span></td>
                    <td>${med.expiry_date ? `<span style="color: #F59E0B; font-weight:bold;">${med.expiry_date}</span>` : '<span style="color: #9CA3AF;">N/A</span>'}</td>
                    <td>
                        <button onclick="adjustStock(${med.id}, '${med.name}')" class="btn btn-primary" style="padding: 4px 8px; font-size: 0.8rem; background: #6B7280; border: none;">Adjust</button>
                    </td>
                </tr>
            `;
            inventoryTableBody.insertAdjacentHTML('beforeend', row);
        });
    } catch (error) {
        console.error('Error fetching inventory:', error);
    }
}

// Nayi medicine form submit hone par API ko POST request bhejna
if (addMedicineForm) {
    addMedicineForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const newMedicine = {
            barcode: document.getElementById('barcode').value,
            name: document.getElementById('name').value,
            generic_name: document.getElementById('generic_name').value,
            purchase_price: parseFloat(document.getElementById('purchase_price').value),
            sale_price: parseFloat(document.getElementById('sale_price').value),
            stock_quantity: parseInt(document.getElementById('stock_quantity').value) || 0,
            expiry_date: document.getElementById('expiry_date').value || null
        };

        try {
            const response = await fetch('/api/inventory/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newMedicine)
            });

            if (response.ok) {
                // Agar successfully save ho jaye
                addMedicineForm.reset();
                document.getElementById('barcode').focus(); // Cursor wapas barcode par taake fast entry ho sake
                loadMedicines(); // Table refresh karo
            } else {
                // Agar backend (FastAPI) koi error de (e.g. duplicate barcode)
                const errData = await response.json();
                alert(`Error: ${errData.detail}`);
            }
        } catch (error) {
            console.error('Error adding medicine:', error);
            alert("Backend se connect karne mein masla aagaya!");
        }
    });

    // Jab web page poora load ho jaye, tab yeh table data fetch karega
    document.addEventListener('DOMContentLoaded', loadMedicines);
    
    // Pagination aur Search Event Listeners
    if (searchInput) {
        // Debounce search so it doesn't fire on every single keystroke immediately
        let timeout = null;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                currentSearch = e.target.value.trim();
                currentPage = 0; // Search karne par pehlay page par wapas le aao
                loadMedicines();
            }, 300);
        });
    }

    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', () => {
            if (currentPage > 0) {
                currentPage--;
                loadMedicines();
            }
        });
    }

    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', () => {
            currentPage++;
            loadMedicines();
        });
    }
}

// Stock Adjustment Logic
async function adjustStock(medicineId, name) {
    const qtyStr = prompt(`"${name}" ka stock adjust karein.\n\nNaye items add karne ke liye + likhein (e.g., 5).\nDamage/Expire nikalne ke liye - likhein (e.g., -2):`);
    if (!qtyStr) return;
    
    const qty = parseInt(qtyStr);
    if (isNaN(qty) || qty === 0) {
        alert("Invalid quantity!");
        return;
    }
    
    const reason = prompt(`Reason for adjustment (e.g., Damaged, Found, Expired)?`);
    if (!reason) return;

    try {
        const response = await fetch(`/api/inventory/${medicineId}/adjust`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                quantity_adjusted: qty,
                reason: reason
            })
        });
        
        const result = await response.json();
        if (response.ok) {
            alert(result.message);
            loadMedicines(); // Refresh table
        } else {
            alert(`Error: ${result.detail}`);
        }
    } catch (error) {
        alert("Error connecting to server!");
        console.error(error);
    }
}