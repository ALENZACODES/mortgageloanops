"""Sample files used by the CLI demo, the web UI and the tests."""
SAMPLES = {
    "purchase_fthb": {"id": "demo-purchase", "type": "FTHB", "province": "ON", "credit_score": 720,
        "borrower": {"name": "Priya Shah", "phone": "+14165550100", "email": "priya@example.com"},
        "price": 750000, "down_payment": 100000, "income": 180000, "contract_rate": 4.5, "property_tax": 4500,
        "amort_years": 30, "postal_code": "M5V 2T6", "purchase_price": 750000, "purchase_year": 2022, "purchase_month": 6},
    "renewal_ird": {"id": "demo-renewal", "type": "RENEWAL", "province": "ON", "credit_score": 700,
        "borrower": {"name": "Daniel Okafor", "phone": "+16475550111", "email": "daniel@example.com"},
        "balance": 400000, "contract_rate": 5.2, "months_remaining": 30, "original_posted_rate": 6.9,
        "current_posted_rate": 5.8, "new_rate": 4.4, "amort_years_remaining": 22, "other_costs": 1500,
        "postal_code": "L4B 1B4", "purchase_price": 640000, "purchase_year": 2019, "purchase_month": 9},
    "declined_stress": {"id": "demo-stress", "type": "PURCHASE", "province": "BC", "credit_score": 690,
        "borrower": {"name": "Mei Lin Chen", "phone": "+16045550122", "email": "meilin@example.com"},
        "price": 900000, "down_payment": 180000, "income": 120000, "contract_rate": 4.6, "property_tax": 3800,
        "other_debt": 600, "amort_years": 25},
}
