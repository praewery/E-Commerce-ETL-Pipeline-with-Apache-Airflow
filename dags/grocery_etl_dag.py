"""
grocery_etl_dag.py
==================
DAG: Grocery ETL Pipeline (Open Food Facts / DummyJSON → PostgreSQL DWH)

Pipeline:
  1. health_check    - เช็คว่า API พร้อมใช้งาน
  2. extract_data    - ดึงข้อมูลจาก API
  3. transform_data  - แปลงข้อมูลให้เข้า Star Schema
  4. load_data       - โหลดข้อมูลลง PostgreSQL
  5. validate        - ตรวจสอบข้อมูลว่าครบถ้วน
  6. notify          - แสดงสรุปผลการรัน
"""

import sys
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# บอก Airflow ว่า scripts อยู่ที่ไหน เพื่อ import ได้
sys.path.insert(0, "/opt/airflow/scripts")


# ---------------------------------------------------------------
# Default Arguments — ค่า default ที่ทุก task ใช้ร่วมกัน
# ---------------------------------------------------------------
default_args = {
    "owner": "data-engineer",
    "depends_on_past": False,       # แต่ละ run ไม่ขึ้นกับ run ก่อนหน้า
    "email_on_failure": False,
    "retries": 2,                   # ถ้า task fail ให้ลองใหม่ 2 ครั้ง
    "retry_delay": timedelta(minutes=5),  # รอ 5 นาทีก่อนลองใหม่
}


# ---------------------------------------------------------------
# TASK 1: health_check — ตรวจสอบว่า API ใช้ได้ก่อนดึงข้อมูล
# ---------------------------------------------------------------
def task_health_check(**context):
    import requests

    # ลอง ping API ด้วย request เล็กๆ (1 สินค้า)
    url = "https://dummyjson.com/products/1"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()  # raise error ถ้า status ไม่ใช่ 200

    logging.info(f"[health_check] API OK — status {resp.status_code}")


# ---------------------------------------------------------------
# TASK 2: extract_data — ดึงข้อมูลจาก API แล้วส่งต่อผ่าน XCom
# ---------------------------------------------------------------
def task_extract(**context):
    from extract import extract_all

    raw = extract_all()  # ดึงข้อมูล products + customers

    # XCom = กล่องส่งข้อมูลระหว่าง task ใน Airflow
    # xcom_push = ใส่ข้อมูลลงกล่อง
    context["ti"].xcom_push(key="raw_data", value=raw)

    logging.info(
        f"[extract] products={len(raw['products'])} "
        f"customers={len(raw['customers'])}"
    )


# ---------------------------------------------------------------
# TASK 3: transform_data — แปลงข้อมูล แล้วส่งต่อผ่าน XCom
# ---------------------------------------------------------------
def task_transform(**context):
    from transform import transform_all

    # xcom_pull = ดึงข้อมูลจากกล่อง (ที่ task extract ใส่ไว้)
    raw = context["ti"].xcom_pull(key="raw_data", task_ids="extract_data")

    data = transform_all(raw)  # แปลงเป็น Star Schema

    # ส่งแต่ละตารางแยกกัน เพราะ XCom มีขนาดจำกัด
    for table, rows in data.items():
        context["ti"].xcom_push(key=f"data_{table}", value=rows)

    counts = {t: len(r) for t, r in data.items()}
    logging.info(f"[transform] Row counts: {counts}")


# ---------------------------------------------------------------
# TASK 4: load_data — โหลดข้อมูลทั้งหมดลง PostgreSQL
# ---------------------------------------------------------------
def task_load(**context):
    from load import (
        get_dwh_connection,
        create_tables,
        load_categories,
        load_products,
        load_customers,
        load_dates,
        load_orders,
    )

    ti = context["ti"]

    # ดึงข้อมูลจาก XCom ที่ transform ส่งมา
    def pull(key):
        return ti.xcom_pull(key=f"data_{key}", task_ids="transform_data")

    categories = pull("categories")
    products   = pull("products")
    customers  = pull("customers")
    dates      = pull("dates")
    orders     = pull("orders")

    conn = get_dwh_connection()
    try:
        create_tables(conn)                                    # สร้างตารางถ้ายังไม่มี
        category_map = load_categories(conn, categories)      # โหลด dim แล้วเก็บ map ชื่อ→id
        product_map  = load_products(conn, products, category_map)
        customer_map = load_customers(conn, customers)
        date_map     = load_dates(conn, dates)
        load_orders(conn, orders, product_map, customer_map, date_map)
        logging.info("[load] All data loaded successfully")
    finally:
        conn.close()  # ปิด connection เสมอ


# ---------------------------------------------------------------
# TASK 5: validate — ตรวจสอบว่า DB มีข้อมูลครบ ไม่มีตารางว่าง
# ---------------------------------------------------------------
def task_validate(**context):
    from load import get_dwh_connection

    # รายการ query ที่จะตรวจสอบ
    checks = {
        "dim_category": "SELECT COUNT(*) FROM dim_category",
        "dim_product":  "SELECT COUNT(*) FROM dim_product",
        "dim_customer": "SELECT COUNT(*) FROM dim_customer",
        "dim_date":     "SELECT COUNT(*) FROM dim_date",
        "fact_orders":  "SELECT COUNT(*) FROM fact_orders",
    }

    conn = get_dwh_connection()
    results = {}
    try:
        with conn.cursor() as cur:
            for table, sql in checks.items():
                cur.execute(sql)
                results[table] = cur.fetchone()[0]  # ดึงตัวเลขแถวแรก คอลัมน์แรก
    finally:
        conn.close()

    logging.info(f"[validate] Row counts: {results}")

    # ถ้าตารางไหนมี 0 แถว ให้ pipeline fail ทันที
    empty = [t for t, count in results.items() if count == 0]
    if empty:
        raise ValueError(f"[validate] Empty tables found: {empty}")

    logging.info("[validate] All checks passed ✓")


# ---------------------------------------------------------------
# TASK 6: notify — แสดงสรุปผลหลัง pipeline เสร็จ
# ---------------------------------------------------------------
def task_notify(**context):
    from load import get_dwh_connection

    conn = get_dwh_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                    AS total_orders,
                    SUM(quantity)               AS total_items,
                    ROUND(SUM(total_amount)::numeric, 2) AS total_revenue
                FROM fact_orders
            """)
            row = cur.fetchone()
    finally:
        conn.close()

    # แสดง summary ใน Airflow logs
    msg = (
        f"\n{'='*45}\n"
        f"  Grocery ETL Pipeline — Complete\n"
        f"  Total Orders  : {row[0]}\n"
        f"  Total Items   : {row[1]}\n"
        f"  Total Revenue : ${row[2]:,.2f}\n"
        f"  Finished at   : {datetime.utcnow().isoformat()}\n"
        f"{'='*45}"
    )
    logging.info(msg)


# ---------------------------------------------------------------
# DAG Definition — ประกาศ pipeline และลำดับการทำงาน
# ---------------------------------------------------------------
with DAG(
    dag_id="grocery_etl_pipeline",
    description="Daily ETL: Open Food Facts → PostgreSQL Star Schema",
    default_args=default_args,
    schedule_interval="0 2 * * *",   # Cron: ทุกวัน 02:00 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,       # ไม่ย้อนรันวันที่ผ่านมาแล้ว
    max_active_runs=1,   # รันได้แค่ครั้งเดียวต่อเวลา
    tags=["grocery", "etl", "data-engineering"],
) as dag:

    # สร้าง task แต่ละตัว โดยระบุ function ที่จะรัน
    health_check   = PythonOperator(task_id="health_check",   python_callable=task_health_check)
    extract_data   = PythonOperator(task_id="extract_data",   python_callable=task_extract)
    transform_data = PythonOperator(task_id="transform_data", python_callable=task_transform)
    load_data      = PythonOperator(task_id="load_data",      python_callable=task_load)
    validate       = PythonOperator(task_id="validate",       python_callable=task_validate)
    notify         = PythonOperator(task_id="notify",         python_callable=task_notify)

    # กำหนดลำดับการทำงานด้วย >> (อ่านว่า "แล้วจึง")
    health_check >> extract_data >> transform_data >> load_data >> validate >> notify
