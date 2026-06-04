import os
import psycopg2  # library เชื่อมต่อ Python กับ PostgreSQL


# ---------------------------------------------------------------
# get_dwh_connection: สร้าง connection ไปยัง Data Warehouse
# ---------------------------------------------------------------
def get_dwh_connection():
    return psycopg2.connect(
        host=os.getenv("DWH_HOST", "localhost"),  # ใน Docker ใช้ "dwh-postgres", local ใช้ "localhost"
        port=os.getenv("DWH_PORT", "5433"),       # Docker map port 5433 ออกมาให้เราใช้
        database=os.getenv("DWH_DB", "grocery_dwh"),
        user=os.getenv("DWH_USER", "dwh_user"),
        password=os.getenv("DWH_PASSWORD", "dwh_password"),
    )


# ---------------------------------------------------------------
# create_tables: อ่านไฟล์ SQL แล้วสร้างตารางทั้งหมดใน DB
# ---------------------------------------------------------------
def create_tables(conn):
    # หาที่อยู่ของไฟล์ SQL (อยู่ใน sql/ folder)
    sql_path = os.path.join(os.path.dirname(__file__), "..", "sql", "create_star_schema.sql")

    with open(sql_path, "r") as f:
        sql = f.read()  # อ่านไฟล์ทั้งหมดเป็น string

    with conn.cursor() as cur:
        cur.execute(sql)   # รัน SQL ทั้งหมดใน string นั้น
    conn.commit()          # บันทึกการเปลี่ยนแปลง
    print("[create_tables] Tables created")


# ---------------------------------------------------------------
# load_categories: INSERT category เข้า dim_category
# return: dict ชื่อ → id เช่น {"beverages": 1, "dairies": 2}
# ---------------------------------------------------------------
def load_categories(conn, categories):
    with conn.cursor() as cur:
        for name in categories:
            cur.execute("""
                INSERT INTO dim_category (category_name)
                VALUES (%s)
                ON CONFLICT (category_name) DO NOTHING
            """, (name,))
            # ON CONFLICT DO NOTHING = ถ้า category ซ้ำ ให้ข้ามไป ไม่ error

        conn.commit()

        # ดึง id กลับมาทำ map ชื่อ → id
        cur.execute("SELECT category_id, category_name FROM dim_category")
        rows = cur.fetchall()  # [(1, "beverages"), (2, "dairies"), ...]

    # แปลงเป็น dict เพื่อค้นหาง่าย: {"beverages": 1, "dairies": 2}
    category_map = {name: cid for cid, name in rows}
    print(f"[load_categories] {len(category_map)} categories loaded")
    return category_map


# ---------------------------------------------------------------
# load_products: INSERT product เข้า dim_product
# ต้องรับ category_map เพื่อแปลงชื่อ category → category_id
# ---------------------------------------------------------------
def load_products(conn, products, category_map):
    with conn.cursor() as cur:
        for p in products:
            # แปลงชื่อ category เป็น id โดยใช้ map
            cid = category_map.get(p["category_name"])

            cur.execute("""
                INSERT INTO dim_product (product_name, brand, nutriscore, category_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (product_name) DO NOTHING
            """, (p["product_name"], p["brand"], p["nutriscore"], cid))

        conn.commit()

        # ดึง id กลับมาทำ map ชื่อ → id
        cur.execute("SELECT product_id, product_name FROM dim_product")
        rows = cur.fetchall()

    product_map = {name: pid for pid, name in rows}
    print(f"[load_products] {len(product_map)} products loaded")
    return product_map


# ---------------------------------------------------------------
# load_customers: INSERT customer เข้า dim_customer
# return: dict email → customer_id
# ---------------------------------------------------------------
def load_customers(conn, customers):
    with conn.cursor() as cur:
        for c in customers:
            cur.execute("""
                INSERT INTO dim_customer (full_name, email, city, country)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (c["full_name"], c["email"], c["city"], c["country"]))

        conn.commit()

        cur.execute("SELECT customer_id, email FROM dim_customer")
        rows = cur.fetchall()

    # map email → customer_id เพราะ email ไม่ซ้ำกัน ใช้เป็น key ได้
    customer_map = {email: cid for cid, email in rows}
    print(f"[load_customers] {len(customer_map)} customers loaded")
    return customer_map


# ---------------------------------------------------------------
# load_dates: INSERT วันที่เข้า dim_date
# return: dict full_date → date_id
# ---------------------------------------------------------------
def load_dates(conn, dates):
    with conn.cursor() as cur:
        for d in dates:
            cur.execute("""
                INSERT INTO dim_date (full_date, year, month, month_name, day, day_name, quarter)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (full_date) DO NOTHING
            """, (
                d["full_date"], d["year"], d["month"], d["month_name"],
                d["day"], d["day_name"], d["quarter"]
            ))

        conn.commit()

        cur.execute("SELECT date_id, full_date FROM dim_date")
        rows = cur.fetchall()

    # map วันที่ → date_id
    date_map = {str(full_date): did for did, full_date in rows}
    print(f"[load_dates] {len(date_map)} dates loaded")
    return date_map


# ---------------------------------------------------------------
# load_orders: INSERT order เข้า fact_orders
# ต้องใช้ map ทั้ง 3 ตัวเพื่อแปลงชื่อ → id
# ---------------------------------------------------------------
def load_orders(conn, orders, product_map, customer_map, date_map):
    inserted = 0
    skipped  = 0

    with conn.cursor() as cur:
        for o in orders:
            # แปลงชื่อ → id โดยใช้ map ที่สร้างไว้
            pid = product_map.get(o["product_name"])
            cid = customer_map.get(o["email"])
            did = date_map.get(str(o["order_date"]))

            # ถ้าหา id ไม่เจอสักตัว ให้ข้ามไป (ข้อมูลไม่สมบูรณ์)
            if not all([pid, cid, did]):
                skipped += 1
                continue

            cur.execute("""
                INSERT INTO fact_orders
                    (date_id, product_id, customer_id, quantity, unit_price, total_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (did, pid, cid, o["quantity"], o["unit_price"], o["total_amount"]))
            inserted += 1

        conn.commit()

    print(f"[load_orders] {inserted} orders inserted, {skipped} skipped")


# ---------------------------------------------------------------
# load_all: รวมทุก function เรียงตามลำดับที่ถูกต้อง
# ---------------------------------------------------------------
def load_all(data):
    conn = get_dwh_connection()  # เปิด connection ครั้งเดียว ใช้ตลอด

    try:
        create_tables(conn)   # 1. สร้างตารางก่อน

        # 2. โหลด dimension tables (ต้องก่อน fact เพราะ fact อ้างอิง FK)
        category_map = load_categories(conn, data["categories"])
        product_map  = load_products(conn, data["products"], category_map)
        customer_map = load_customers(conn, data["customers"])
        date_map     = load_dates(conn, data["dates"])

        # 3. โหลด fact table สุดท้าย
        load_orders(conn, data["orders"], product_map, customer_map, date_map)

        print("\n[load_all] Pipeline complete!")

    finally:
        conn.close()  # ปิด connection เสมอ ไม่ว่าจะ error หรือไม่


# ---------------------------------------------------------------
# ทดสอบ: รัน python load.py โดยตรง
# ---------------------------------------------------------------
if __name__ == "__main__":
    from extract import extract_all
    from transform import transform_all

    print("Extracting...")
    raw  = extract_all()

    print("Transforming...")
    data = transform_all(raw)

    print("Loading...")
    load_all(data)
