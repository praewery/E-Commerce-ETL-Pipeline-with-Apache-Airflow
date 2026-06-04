CREATE TABLE IF NOT EXISTS dim_category (
    category_id   SERIAL        PRIMARY KEY,
    category_name VARCHAR(200)  NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS dim_date (
    date_id    SERIAL        PRIMARY KEY,
    full_date DATE          NOT NULL UNIQUE,
    year      INT           NOT NULL,
    month     INT           NOT NULL,
    month_name VARCHAR(20)   NOT NULL,
    day       INT           NOT NULL,
    day_name   VARCHAR(20)   NOT NULL,
    quarter   INT           NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_product (
    product_id   SERIAL        PRIMARY KEY,
    product_name VARCHAR(200)  NOT NULL UNIQUE,
    brand       VARCHAR(100)  ,
    nutriscore    CHAR(1)     ,
    category_id  INT           NOT NULL,
    FOREIGN KEY (category_id) REFERENCES dim_category(category_id)
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id SERIAL        PRIMARY KEY,
    full_name   VARCHAR(200)  NOT NULL,
    email       VARCHAR(200)  NOT NULL,
    city        VARCHAR(100)  NOT NULL,
    country     VARCHAR(100)  NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id     SERIAL        PRIMARY KEY,
    date_id      INT           NOT NULL,
    product_id   INT           NOT NULL,
    customer_id  INT           NOT NULL,
    quantity     INT           NOT NULL,
    unit_price   DECIMAL(10, 2) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id)
);
