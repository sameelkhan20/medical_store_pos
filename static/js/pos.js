// --- POS / BILLING LOGIC ---

let cart = [];

const scannerInput = document.getElementById('barcodeScanner');
const cartTableBody = document.getElementById('cartTableBody');
const subtotalAmount = document.getElementById('subtotalAmount');
const discountInput = document.getElementById('discountInput');
const finalAmount = document.getElementById('finalAmount');
const checkoutBtn = document.getElementById('checkoutBtn');

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

    if (medicine.stock_quantity <= 0) {
        alert(`"${medicine.name}" out of stock hai!`);
        return;
    }

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
    finalAmount.innerText = `Rs. ${final.toFixed(2)}`;
}

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

    // Backend ko jo data bhejna hai usko prepare karein
    const checkoutData = {
        items: cart.map(item => ({ barcode: item.barcode, quantity: item.quantity })),
        discount: parseFloat(discountInput.value) || 0
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