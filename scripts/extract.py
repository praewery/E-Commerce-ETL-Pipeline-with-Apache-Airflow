import requests

def extract_products():
    # ลอง Open Food Facts ก่อน ถ้าล้มเหลวให้ใช้ DummyJSON แทน
    off_url = "https://world.openfoodfacts.org/api/v2/search?fields=product_name,brands,categories_tags,nutriscore_grade&page_size=100"
    headers = {"User-Agent": "GroceryETL/1.0 (learning project)"}
    try:
        response = requests.get(off_url, headers=headers, timeout=15)
        response.raise_for_status()
        products = response.json().get("products", [])
        if products:
            print("[extract] Using Open Food Facts API")
            return products
    except Exception:
        pass

    # Fallback: DummyJSON — โครงสร้างต่างกันนิดหน่อย ต้องแปลงให้ตรง
    print("[extract] Open Food Facts unavailable, using DummyJSON fallback")
    response = requests.get("https://dummyjson.com/products?limit=100", timeout=15)
    response.raise_for_status()
    raw = response.json().get("products", [])
    # แปลง DummyJSON format → Open Food Facts format
    return [
        {
            "product_name":    p["title"],
            "brands":          p.get("brand", ""),
            "categories_tags": [f"en:{p.get('category', 'uncategorized').lower().replace(' ', '-')}"],
            "nutriscore_grade": None,
        }
        for p in raw
    ]


def extract_customers():
    # ดึงข้อมูลลูกค้าจาก RandomUser.me
    response = requests.get("https://randomuser.me/api/?results=10")
    data = response.json()
    # return list ของ customers
    return data.get("results", [])

def extract_all():
    # เรียก 2 function ข้างบน
    # return {"products": [...], "customers": [...]}
    return {
        "products": extract_products(),
        "customers": extract_customers()
    }
if __name__ == "__main__":
    data = extract_all()
    print(f"Products: {len(data['products'])} items")
    print(f"Customers: {len(data['customers'])} items")
    print("\nตัวอย่างสินค้าแรก:", data['products'][0].get('product_name'))
    print("ตัวอย่างลูกค้าแรก:", data['customers'][0]['name']['first'])
