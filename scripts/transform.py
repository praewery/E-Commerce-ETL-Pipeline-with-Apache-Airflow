import pandas as pd                    # library สำหรับจัดการข้อมูลแบบตาราง (ใช้ใน load.py)
import random                          # สุ่มตัวเลข/เลือก element แบบสุ่ม
from datetime import datetime, timedelta  # datetime = วันที่+เวลา, timedelta = ระยะเวลา เช่น 3 วัน


# ---------------------------------------------------------------
# transform_categories: แปลง raw products → list ของชื่อ category
# ---------------------------------------------------------------
def transform_categories(products):
    categories = set()  # ใช้ set เพื่อไม่ให้ category ซ้ำกัน

    for product in products:
        # .get("categories_tags", []) = ดึง field นี้ออกมา ถ้าไม่มีให้ใช้ [] แทน
        tags = product.get("categories_tags", [])

        if tags:  # ถ้ามี tag อย่างน้อย 1 ตัว
            category = tags[0]  # เอาแค่ category แรก เช่น "en:dairies"
            # ตัด "en:" ออก และแทน "-" ด้วยช่องว่าง → "dairies", "fermented foods"
            category = category.replace("en:", "").replace("-", " ")
            categories.add(category)  # เพิ่มเข้า set (ถ้าซ้ำจะไม่เพิ่ม)

    return list(categories)  # แปลง set กลับเป็น list ก่อน return


# ---------------------------------------------------------------
# transform_products: แปลง raw products → list ของ dict พร้อม load
# ---------------------------------------------------------------
def transform_products(products):
    result = []  # list เก็บ product ที่แปลงแล้ว

    for p in products:
        # .strip() = ตัด space หน้า-หลังออก
        name = p.get("product_name", "").strip()

        if not name:   # ถ้าไม่มีชื่อสินค้า ให้ข้ามไปเลย ไม่เอาเข้า DB
            continue

        # category: เอา tag แรก ตัด "en:" และ "-" ออก
        # ถ้าไม่มี tags เลย ให้ใช้ "uncategorized" แทน
        tags = p.get("categories_tags", [])
        category = tags[0].replace("en:", "").replace("-", " ") if tags else "uncategorized"

        # brand: บาง product มีหลาย brand คั่นด้วย "," เช่น "Danone, Nestle"
        # .split(",")[0] = ตัดเอาแค่ตัวแรก → "Danone"
        # .strip() = ตัด space → "Danone" (ไม่มี space นำหน้า)
        brands_raw = p.get("brands", "")
        brand = brands_raw.split(",")[0].strip() if brands_raw else None  # None = ไม่มีข้อมูล

        # nutriscore: ต้องเป็นตัวอักษรเดียว a/b/c/d/e เท่านั้น
        # ถ้าค่าไม่ใช่ตัวอักษรเดียว (เช่น "not-applicable") ให้ใช้ None แทน
        nutriscore_raw = p.get("nutriscore_grade")
        valid_scores = {"a", "b", "c", "d", "e"}
        nutriscore = nutriscore_raw if nutriscore_raw in valid_scores else None

        result.append({
            "product_name":  name,
            "brand":         brand,
            "nutriscore":    nutriscore,
            "category_name": category,
        })

    return result


# ---------------------------------------------------------------
# transform_customers: แปลง raw customers → list ของ dict พร้อม load
# ---------------------------------------------------------------
def transform_customers(customers):
    result = []

    for c in customers:
        result.append({
            # f-string รวมชื่อ first + last เข้าด้วยกัน เช่น "Shilpa Patel"
            "full_name": f"{c['name']['first']} {c['name']['last']}",
            "email":     c["email"],
            # location เป็น dict ซ้อนกัน ต้องเข้าถึง 2 ชั้น
            "city":      c["location"]["city"],
            "country":   c["location"]["country"],
        })

    return result


# ---------------------------------------------------------------
# simulate_orders: สร้าง orders สมมติโดยสุ่มจับคู่ product + customer
# ---------------------------------------------------------------
def simulate_orders(products, customers, n=200):
    # n=200 คือ default สร้าง 200 orders ถ้าไม่ระบุ n
    orders = []
    today = datetime.today()  # วันที่วันนี้

    for _ in range(n):  # _ หมายถึงไม่ใช้ตัวแปร loop นี้
        product  = random.choice(products)   # สุ่มเลือก 1 product จาก list
        customer = random.choice(customers)  # สุ่มเลือก 1 customer จาก list

        qty   = random.randint(1, 5)                  # จำนวนสินค้า 1-5 ชิ้น
        price = round(random.uniform(10, 500), 2)     # ราคาสุ่ม 10-500 บาท ทศนิยม 2 ตำแหน่ง

        # timedelta(days=X) = ลบ X วันออกจากวันนี้
        # .date() = ตัดเวลาออก เหลือแค่วันที่ เช่น 2026-05-15
        order_date = (today - timedelta(days=random.randint(0, 90))).date()

        orders.append({
            "product_name":  product["product_name"],
            "category_name": product["category_name"],
            "full_name":     customer["full_name"],
            "email":         customer["email"],
            "quantity":      qty,
            "unit_price":    price,
            "total_amount":  round(qty * price, 2),  # ราคารวม = จำนวน × ราคาต่อชิ้น
            "order_date":    order_date,
        })

    return orders


# ---------------------------------------------------------------
# transform_dates: ดึงวันที่ unique จาก orders → list ของ dict
# ---------------------------------------------------------------
def transform_dates(orders):
    seen = {}  # dict ใช้เก็บวันที่ที่เจอแล้ว (key=วันที่, value=dict ข้อมูล)

    for o in orders:
        d = o["order_date"]  # ดึงวันที่จาก order

        if d not in seen:  # ถ้ายังไม่เคยเจอวันนี้มาก่อน
            seen[d] = {
                "full_date":  d,
                "year":       d.year,              # ปี เช่น 2026
                "month":      d.month,             # เดือน 1-12
                "month_name": d.strftime("%B"),    # ชื่อเดือน เช่น "June"
                "day":        d.day,               # วันที่ 1-31
                "day_name":   d.strftime("%A"),    # ชื่อวัน เช่น "Monday"
                # quarter: (month-1)//3 + 1
                # เดือน 1-3 → Q1, 4-6 → Q2, 7-9 → Q3, 10-12 → Q4
                "quarter":    (d.month - 1) // 3 + 1,
            }

    return list(seen.values())  # เอาแค่ values (dict) ออกมาเป็น list


# ---------------------------------------------------------------
# transform_all: รวมทุก function → return dict ของทุก table
# ---------------------------------------------------------------
def transform_all(raw):
    # raw มี key: "products" และ "customers" (มาจาก extract_all)
    products   = transform_products(raw["products"])
    customers  = transform_customers(raw["customers"])
    categories = transform_categories(raw["products"])  # ดึง category จาก products
    orders     = simulate_orders(products, customers)   # สร้าง orders สมมติ
    dates      = transform_dates(orders)                # ดึงวันที่ unique จาก orders

    return {
        "categories": categories,
        "products":   products,
        "customers":  customers,
        "orders":     orders,
        "dates":      dates,
    }


# ---------------------------------------------------------------
# ทดสอบ: รัน python transform.py โดยตรง
# ---------------------------------------------------------------
if __name__ == "__main__":
    from extract import extract_all          # import จากไฟล์ extract.py
    raw  = extract_all()                     # ดึงข้อมูลจาก API
    data = transform_all(raw)               # แปลงข้อมูล

    print(f"Categories : {len(data['categories'])}")
    print(f"Products   : {len(data['products'])}")
    print(f"Customers  : {len(data['customers'])}")
    print(f"Orders     : {len(data['orders'])}")
    print(f"Dates      : {len(data['dates'])}")
    print("\nตัวอย่าง order:", data['orders'][0])
