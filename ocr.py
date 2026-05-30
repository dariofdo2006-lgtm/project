import re
import io
from PIL import Image, ImageOps
import pytesseract

def guess_category_from_text(text):
    """Enhanced category guessing with transaction type detection"""
    t = text.lower()
    
    # Check if this is an expense or income receipt
    income_keywords = [
        "salary", "income", "credit", "refund", "bonus", "stipend", "wage",
        "deposit", "cashback", "dividend", "interest", "pension"
    ]
    
    # If income keywords found, it's likely an income transaction
    if any(keyword in t for keyword in income_keywords):
        return "Income"
    
    # Otherwise, categorize as expense
    # Simplified category keywords
    expense_category_keywords = {
        "Food": ["restaurant", "cafe", "food", "pizza", "burger", "coffee", "meal"],
        "Grocery": ["grocery", "supermarket", "mart", "vegetable", "fruit", "dairy"],
        "Transportation": ["uber", "taxi", "fuel", "petrol", "gas", "bus", "train"],
        "Shopping": ["amazon", "shopping", "store", "purchase", "product"],
        "Utilities": ["electricity", "water", "internet", "phone", "bill"],
        "Healthcare": ["hospital", "clinic", "pharmacy", "medical", "medicine"],
        "Entertainment": ["movie", "netflix", "game", "concert", "show"],
        "Education": ["school", "college", "tuition", "course", "book"]
    }
    
    for category, keywords in expense_category_keywords.items():
        if any(w in t for w in keywords):
            return category
    
    return "Other"

def extract_amount_from_text(text):
    """Improved amount extraction for Indian receipts"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    
    # Priority keywords for total lines (more specific)
    priority_keywords = [
        "total", "amount due", "grand total", "final total", "payable", "sum"
    ]
    
    # Multiple amount patterns to catch different formats including INR
    amount_patterns = [
        r"[₹$]\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})",  # ₹1,234.56 or $1,234.56
        r"[₹$]?(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})",  # 1,234.56 or 1234.56
        r"[₹$]\s*(\d+\.\d{2})",                              # ₹123.45 or $123.45
        r"[₹$]?(\d+\.\d{2})",                                 # 123.45 or ₹123.45
        r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})",      # 1,234.56 or 1234.56
    ]

    def to_float(raw):
        try:
            cleaned = re.sub(r'[^\d.]', '', raw)
            return float(cleaned)
        except Exception:
            return None

    # First, try lines with total keywords
    for ln in lines:
        ln_lower = ln.lower()
        if any(keyword in ln_lower for keyword in priority_keywords):
            for pattern in amount_patterns:
                matches = re.findall(pattern, ln)
                if matches:
                    for match in reversed(matches):
                        val = to_float(match)
                        if val is not None and 0 < val < 100000:
                            return val

    # Look for lines that might be totals (last lines with reasonable amounts)
    for ln in reversed(lines):  # Check from bottom up
        for pattern in amount_patterns:
            matches = re.findall(pattern, ln)
            if matches:
                for match in matches:
                    val = to_float(match)
                    # Look for reasonable total amounts (typically > ₹5)
                    if val is not None and 5 < val < 100000:
                        # If this is the last line or near the end, it's likely the total
                        if len(lines) - lines.index(ln) <= 3:  # Within last 3 lines
                            return val
    
    # If no total found, look for the largest reasonable amount
    all_amounts = []
    for ln in lines:
        for pattern in amount_patterns:
            matches = re.findall(pattern, ln)
            for match in matches:
                val = to_float(match)
                if val is not None and 5 < val < 100000:
                    all_amounts.append(val)
    
    if all_amounts:
        return max(all_amounts)
    
    return None

def extract_items_from_text(text):
    """Extract item list from receipt text (optimized for Indian receipts)"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = []
    
    # Skip lines that are definitely not items
    skip_tokens = (
        "total", "subtotal", "tax", "gst", "vat", "cash", "credit", "debit",
        "change", "balance", "due", "paid", "receipt", "invoice", "bill",
        "date", "time", "thank you", "phone", "tel", "www", "http", "email",
        "order", "table", "customer"
    )
    
    for ln in lines:
        low = ln.lower()
        
        # Skip lines with skip tokens
        if any(tok in low for tok in skip_tokens):
            continue
            
        # Skip lines that are just totals (like "70" or "₹70")
        if re.match(r'^[₹$]?\d+(?:,\d{3})*(?:\.\d{2})?$', ln.strip()):
            continue
            
        # Skip lines that are too short or too long
        if len(ln) < 3 or len(ln) > 80:
            continue
            
        # Skip lines with no letters (just numbers/symbols)
        if not re.search(r'[a-zA-Z]', ln):
            continue
            
        # Look for Indian receipt item patterns like "1x Veg Sandwich ₹50"
        item_pattern = r'(\d+x)?\s*([a-zA-Z][^₹$]*?)\s*[₹$]?\d+(?:,\d{3})*(?:\.\d{2})?'
        match = re.search(item_pattern, ln)
        if match:
            quantity = match.group(1) or "1x"
            item_name = match.group(2).strip()
            if item_name:
                items.append(f"{quantity} {item_name}")
            continue
            
        # If no pattern match, but line has letters and reasonable length, include it
        if len(re.findall(r'\d', ln)) <= 3:  # Not too many numbers
            items.append(ln.strip())
        
        # Limit to reasonable number of items
        if len(items) >= 15:
            break
    
    return items

def extract_name_from_text(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    
    # Skip tokens that are definitely not store names
    skip_tokens = (
        "invoice", "bill", "receipt", "date", "time", "gst", "tax", "vat",
        "phone", "tel", "www", "http", "email", "thank you", "cash", "credit",
        "debit", "card", "change", "balance", "item", "qty", "quantity"
    )
    
    # Look for potential store names in first few lines
    for ln in lines[:8]:
        low = ln.lower()
        
        # Skip lines with skip tokens
        if any(tok in low for tok in skip_tokens):
            continue
            
        # Skip lines with too many numbers
        if len(re.findall(r'\d', ln)) > 4:
            continue
            
        # Skip lines that are too short or too long
        if len(ln) < 3 or len(ln) > 50:
            continue
            
        return ln.strip()
    
    return "Receipt Purchase"

def scan_receipt_locally(file_bytes):
    if not Image or not ImageOps or not pytesseract:
        return None, "Local OCR dependencies missing. Install Pillow and pytesseract."
    try:
        # Open and preprocess image for better OCR accuracy
        image = Image.open(io.BytesIO(file_bytes))
        
        # Convert to grayscale
        gray = ImageOps.grayscale(image)
        
        # Resize for better OCR (scale up if too small)
        width, height = gray.size
        if max(width, height) < 1000:
            scale_factor = 1000 / max(width, height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            gray = gray.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Apply multiple enhancement techniques
        # 1. Auto contrast for better text visibility
        enhanced = ImageOps.autocontrast(gray)
        
        # 2. Binarization for clearer text
        threshold = 128
        binary = enhanced.point(lambda x: 0 if x < threshold else 255, '1')
        
        # 3. Denoising using median filter
        from PIL import ImageFilter
        denoised = binary.filter(ImageFilter.MedianFilter(size=3))
        
        # Convert back to grayscale for Tesseract
        final_image = denoised.convert('L')
        
        # Use simple, reliable Tesseract configuration
        try:
            text = pytesseract.image_to_string(final_image, config="--psm 6 --oem 3")
        except Exception as e:
            # Fallback to basic configuration
            text = pytesseract.image_to_string(final_image, config="--psm 6")
        
        if not text or not text.strip():
            return None, "Could not read text from receipt image."
        
        # Enhanced amount extraction
        amount = extract_amount_from_text(text)
        name = extract_name_from_text(text)
        category = guess_category_from_text(text)
        items = extract_items_from_text(text)
        transaction_type = "Income" if category == "Income" else "Expense"
        
        # Create description with items if available
        description = name
        if items:
            items_str = ", ".join(items[:5])  # Limit to first 5 items
            if len(items) > 5:
                items_str += f" and {len(items) - 5} more items"
            description = f"{name} - {items_str}"
        
        return {
            "name": name,
            "amount": amount,
            "category": category,
            "description": description,
            "type": transaction_type
        }, None
        
    except Exception as e:
        return None, f"Local OCR failed: {e}"
