// --- POS / BILLING LOGIC ---

let cart = [];

const scannerInput = document.getElementById('barcodeScanner');
const cartTableBody = document.getElementById('cartTableBody');
const subtotalAmount = document.getElementById('subtotalAmount');
const discountInput = document.getElementById('discountInput');
const cashReceivedInput = document.getElementById('cashReceivedInput');
const changeAmount = document.getElementById('changeAmount');
const finalAmount = document.getElementById('finalAmount');
const checkoutBtn = document.getElementById('checkoutBtn');

let currentFinalAmount = 0;

// 2. Barcode Scanner Input Listener (Enter key press ka wait karna)
scannerInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const scannedCode = e.target.value.trim();
        
        if (scannedCode) {
            addItemToCart(scannedCode);
        }
        // Agli scan ke liye field ko fauran khali kar do
        e.target.value = '';
    }
});

// 3. Cart mein item add karna aur stock check karna
async function addItemToCart(barcode) {
    let medicine = null;
    
    // Server se API query karke exact medicine check karein
    try {
        const response = await fetch(`/api/inventory/?search_query=${encodeURIComponent(barcode)}&limit=1`);
        const data = await response.json();
        if (data.length > 0) {
            // First match use karein (Ideally barcode match karega)
            medicine = data[0];
        }
    } catch (error) {
        console.error("Fetch error:", error);
    }
    
    if (!medicine || (medicine.barcode !== barcode)) {
        alert(`Barcode "${barcode}" ki koi medicine system mein nahi mili!`);
        return;
    }

    // Expiry Check Alert
    if (medicine.expiry_date) {
        const today = new Date();
        const expDate = new Date(medicine.expiry_date);
        
        // Remove time portion for accurate date comparison
        today.setHours(0,0,0,0);
        expDate.setHours(0,0,0,0);

        if (expDate < today) {
            alert(`🛑 ALERT: "${medicine.name}" is EXPIRED! (Expiry: ${medicine.expiry_date}). You cannot sell this item.`);
            return;
        } else {
            // Optional: warning if expiring within 30 days
            const diffTime = expDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            if (diffDays <= 30) {
                // Just a soft warning, let them sell but notify
                alert(`⚠️ WARNING: "${medicine.name}" is expiring in ${diffDays} days (Expiry: ${medicine.expiry_date}).`);
            }
        }
    }

    if (medicine.stock_quantity <= 0) {
        alert(`"${medicine.name}" out of stock hai!`);
        
        // Fetch Alternatives
        if(medicine.generic_name && medicine.generic_name !== 'null') {
            try {
                const altRes = await fetch(`/api/inventory/alternatives/${encodeURIComponent(medicine.generic_name)}`);
                const altData = await altRes.json();
                const altDiv = document.getElementById('alternativesDiv');
                
                if(altData.length > 0) {
                    let html = `<strong><i class="fa-solid fa-lightbulb"></i> Alternatives for ${medicine.name} (Formula: ${medicine.generic_name}):</strong><ul style="margin: 5px 0 0 20px;">`;
                    altData.forEach(alt => {
                        html += `<li>${alt.name} - Stock: ${alt.stock_quantity} (Rs. ${alt.sale_price})</li>`;
                    });
                    html += `</ul>`;
                    altDiv.innerHTML = html;
                    altDiv.style.display = 'block';
                }
            } catch(e) { console.error(e); }
        }
        return;
    }
    
    // Hide alternatives div if it was shown previously
    document.getElementById('alternativesDiv').style.display = 'none';

    // Check karein ke item pehle se cart mein toh nahi
    const existingItem = cart.find(item => item.barcode === barcode);
    
    if (existingItem) {
        // Agar pehle se hai toh sirf quantity barhao (stock limit ke andar)
        if (existingItem.quantity + 1 > medicine.stock_quantity) {
            alert(`Stock available nahi! Sirf ${medicine.stock_quantity} bache hain.`);
            return;
        }
        existingItem.quantity++;
    } else {
        // Naya item cart mein daalo
        cart.push({ ...medicine, quantity: 1 });
    }

    renderCart();
}

// 4. Cart ko HTML Table mein render karna
function renderCart() {
    cartTableBody.innerHTML = '';
    let subtotal = 0;

    cart.forEach((item, index) => {
        const itemTotal = item.sale_price * item.quantity;
        subtotal += itemTotal;

        const row = `
            <tr>
                <td><strong>${item.name}</strong></td>
                <td>Rs. ${item.sale_price}</td>
                <td>
                    <input type="number" class="qty-input" value="${item.quantity}" min="1" max="${item.stock_quantity}" onchange="updateQuantity(${index}, this.value)">
                </td>
                <td style="font-weight: bold;">Rs. ${itemTotal.toFixed(2)}</td>
                <td>
                    <button onclick="removeFromCart(${index})" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
        cartTableBody.insertAdjacentHTML('beforeend', row);
    });

    updateTotals(subtotal);
}

// Quantity manually change karna
window.updateQuantity = function(index, newQty) {
    const qty = parseInt(newQty);
    if (qty > cart[index].stock_quantity) {
        alert(`Maximum available stock ${cart[index].stock_quantity} hai!`);
        cart[index].quantity = cart[index].stock_quantity;
    } else if (qty < 1) {
        cart[index].quantity = 1;
    } else {
        cart[index].quantity = qty;
    }
    renderCart();
};

// Item ko cart se delete karna
window.removeFromCart = function(index) {
    cart.splice(index, 1);
    renderCart();
};

// 5. Totals aur Discount Update karna
function updateTotals(subtotal) {
    subtotalAmount.innerText = `Rs. ${subtotal.toFixed(2)}`;
    
    let discount = parseFloat(discountInput.value) || 0;
    
    // Discount agar subtotal se zyada ho jaye toh fix karna
    if (discount > subtotal) {
        discount = subtotal;
        discountInput.value = discount;
    }

    const final = subtotal - discount;
    currentFinalAmount = final;
    finalAmount.innerText = `Rs. ${final.toFixed(2)}`;
    calculateChange();
}

function calculateChange() {
    let received = parseFloat(cashReceivedInput.value) || 0;
    if (received > 0 && received >= currentFinalAmount) {
        changeAmount.innerText = `Rs. ${(received - currentFinalAmount).toFixed(2)}`;
        changeAmount.style.color = 'var(--success)';
    } else {
        changeAmount.innerText = `Rs. 0.00`;
        changeAmount.style.color = '#60A5FA';
    }
}

cashReceivedInput.addEventListener('input', calculateChange);

// Agar user discount type kare toh final total update ho
discountInput.addEventListener('input', () => {
    // Current subtotal dobara calculate kar ke totals update karein
    const subtotal = cart.reduce((sum, item) => sum + (item.sale_price * item.quantity), 0);
    updateTotals(subtotal);
});

// 6. Checkout Process (API par bhejna)
checkoutBtn.addEventListener('click', async () => {
    if (cart.length === 0) {
        alert("Cart bilkul khali hai!");
        return;
    }

    const paymentMethod = document.getElementById('paymentMethod').value;
    const customerPhone = document.getElementById('customerPhone').value;
    
    if (paymentMethod === 'udhar' && !customerPhone) {
        alert("Udhar ke liye Customer Phone Number dena zaroori hai!");
        return;
    }

    // Backend ko jo data bhejna hai usko prepare karein
    const checkoutData = {
        items: cart.map(item => ({ barcode: item.barcode, quantity: item.quantity })),
        discount: parseFloat(discountInput.value) || 0,
        payment_method: paymentMethod,
        customer_phone: customerPhone
    };

    try {
        const response = await fetch('/api/pos/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(checkoutData)
        });

        const result = await response.json();

        if (response.ok) {
            alert(`Checkout Successful!\nBill Number: ${result.bill_number}\nTotal Bill: Rs. ${result.final_amount}`);
            
            // Cart khali karein aur page reset karein
            cart = [];
            discountInput.value = 0;
            cashReceivedInput.value = 0;
            changeAmount.innerText = `Rs. 0.00`;
            document.getElementById('customerPhone').value = '';
            document.getElementById('paymentMethod').value = 'cash';
            document.getElementById('customerPhoneRow').style.display = 'none';
            renderCart();
            
            // Yahan se aage chalkar hum receipt print screen ko open karenge
            window.open(`/receipt/${result.bill_number}`, '_blank');
            
        } else {
            alert(`Error: ${result.detail}`);
        }
    } catch (error) {
        console.error('Checkout error:', error);
        alert("Backend se connect karne mein masla aaya!");
    }
});

// 7. Hold / Resume Bill Logic
let heldBills = JSON.parse(localStorage.getItem('heldBills')) || [];

function renderHeldBills() {
    const list = document.getElementById('heldBillsList');
    if (!list) return;
    list.innerHTML = '';
    
    if (heldBills.length === 0) {
        list.innerHTML = '<p style="color: #9CA3AF;">No bills on hold.</p>';
        return;
    }
    
    heldBills.forEach((bill, index) => {
        const div = document.createElement('div');
        div.style = "padding: 15px; background: #F3F4F6; margin-bottom: 5px; border-radius: 8px; border-left: 4px solid #F59E0B; display: flex; justify-content: space-between; align-items: center;";
        div.innerHTML = `
            <div>
                <strong>Bill #${index + 1}</strong><br>
                <small style="color: #6B7280;">${new Date(bill.timestamp).toLocaleTimeString()} - ${bill.cart.length} items</small>
            </div>
            <div style="display: flex; gap: 5px;">
                <button onclick="resumeBill(${index})" class="btn btn-primary" style="padding: 6px 12px; font-size: 0.8rem; border: none; cursor: pointer;">Resume</button>
                <button onclick="deleteHeldBill(${index})" class="btn badge-danger" style="padding: 6px 12px; font-size: 0.8rem; border:none; cursor:pointer;"><i class="fa-solid fa-trash"></i></button>
            </div>
        `;
        list.appendChild(div);
    });
}

window.holdBill = function() {
    if (cart.length === 0) {
        alert("Cart khali hai, hold nahi kiya ja sakta!");
        return;
    }
    
    heldBills.push({
        cart: [...cart],
        discount: parseFloat(discountInput.value) || 0,
        timestamp: new Date().toISOString()
    });
    localStorage.setItem('heldBills', JSON.stringify(heldBills));
    
    // Clear current cart
    cart = [];
    discountInput.value = 0;
    renderCart();
    renderHeldBills();
};

window.resumeBill = function(index) {
    if (cart.length > 0) {
        if(!confirm("Current cart khali ho jayega! Kya aap waqai isay resume karna chahtay hain?")) return;
    }
    
    const b = heldBills[index];
    cart = [...b.cart];
    discountInput.value = b.discount || 0;
    
    // Remove from held
    heldBills.splice(index, 1);
    localStorage.setItem('heldBills', JSON.stringify(heldBills));
    
    renderCart();
    renderHeldBills();
};

window.deleteHeldBill = function(index) {
    if (confirm("Are you sure you want to delete this held bill permanently?")) {
        heldBills.splice(index, 1);
        localStorage.setItem('heldBills', JSON.stringify(heldBills));
        renderHeldBills();
    }
};

// Page load par held bills render karein
document.addEventListener('DOMContentLoaded', renderHeldBills);

// 8. Quick Actions (Reprint & Refund)
window.reprintBill = function() {
    const billNumber = document.getElementById('reprintBillNumber').value.trim();
    if (!billNumber) {
        alert("Please enter a valid Bill Number!");
        return;
    }
    window.open(`/receipt/${billNumber}`, '_blank');
};

window.refundBillUI = async function() {
    const billNumber = document.getElementById('refundBillNumber').value.trim();
    if (!billNumber) {
        alert("Please enter a valid Bill Number to refund!");
        return;
    }
    
    if(!confirm(`Are you sure you want to refund bill ${billNumber}? This cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/pos/refund/${billNumber}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            alert(result.message);
            document.getElementById('refundBillNumber').value = '';
        } else {
            alert(`Error: ${result.detail}`);
        }
    } catch (error) {
        console.error('Refund error:', error);
        alert("Backend se connect karne mein masla aaya!");
    }
};