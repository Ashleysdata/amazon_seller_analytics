"""Static product catalog for the simulated Amazon seller account.

The brand is fictional ("Northbay Home"). Prices, costs and fees are
illustrative values in the range a small private-label FBA seller would see.
"""

PRODUCTS = [
    # sku, asin, title, category, price, unit_cost, fba_fee, base_daily_units, lead_time_days
    ("NBH-KT-001", "B0CK1T0001", "Silicone Spatula Set (5 pc)", "Kitchen", 19.99, 4.10, 4.25, 22, 12),
    ("NBH-KT-002", "B0CK1T0002", "Bamboo Cutting Board (Large)", "Kitchen", 29.99, 7.80, 5.40, 14, 14),
    ("NBH-KT-003", "B0CK1T0003", "Glass Meal Prep Containers (10 pk)", "Kitchen", 34.99, 9.60, 6.10, 18, 14),
    ("NBH-HM-001", "B0CH0M0001", "Linen Throw Pillow Covers (2 pk)", "Home", 24.99, 5.20, 4.75, 16, 10),
    ("NBH-HM-002", "B0CH0M0002", "Under-Bed Storage Bags (3 pk)", "Home", 27.99, 6.40, 5.90, 12, 12),
    ("NBH-HM-003", "B0CH0M0003", "Motion Sensor Closet Lights (4 pk)", "Home", 21.99, 5.10, 4.40, 20, 16),
    ("NBH-BT-001", "B0CB3T0001", "Jade Facial Roller & Gua Sha Set", "Beauty", 16.99, 2.90, 3.95, 25, 10),
    ("NBH-BT-002", "B0CB3T0002", "Satin Pillowcase (Queen, 2 pk)", "Beauty", 18.99, 3.70, 4.10, 19, 12),
    ("NBH-PT-001", "B0CP3T0001", "Dog Lick Mat (2 pk)", "Pet", 14.99, 2.40, 3.80, 30, 10),
    ("NBH-PT-002", "B0CP3T0002", "Cat Window Perch", "Pet", 32.99, 8.90, 6.30, 9, 15),
    ("NBH-PT-003", "B0CP3T0003", "Pet Hair Remover Roller", "Pet", 23.99, 4.60, 4.50, 24, 12),
    ("NBH-OF-001", "B0C0FF0001", "Monitor Stand Riser with Drawer", "Office", 39.99, 11.20, 7.20, 11, 16),
]

PRODUCT_COLUMNS = [
    "sku", "asin", "title", "category", "list_price", "unit_cost",
    "fba_fee", "base_daily_units", "lead_time_days",
]

REFERRAL_FEE_RATE = 0.15  # Amazon referral fee for most of these categories

# One Sponsored Products campaign per SKU, plus a targeting type
CAMPAIGN_TYPES = ["Auto", "Exact", "Phrase"]
